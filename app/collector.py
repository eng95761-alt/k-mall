"""Periodic read-only collection from the mall routers.

- method "api": RouterOS API through the tunnel (identity, resources, hotspot
  active count, User Manager counts). Read-only allowlist enforced in routeros.py.
- method "tcp": reachability + latency only (routers where API is not available).
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import delete, select

from .config import RouterDef, Settings
from .db import Alert, Router, Sample, utcnow
from .net import tcp_probe
from .routeros import RouterOSApi, RouterOSError

log = logging.getLogger("kmall.collector")

OFFLINE_AFTER_FAILS = 2
CPU_WARN = 90
STORAGE_WARN_PCT = 10


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def collect_one(r: RouterDef, s: Settings) -> dict:
    """Runs in a worker thread. Never raises; returns a result dict."""
    out = {"online": False, "latency_ms": None, "error": None}
    try:
        if r.method == "tcp":
            out["latency_ms"] = round(tcp_probe(r.host, r.port, s.socks), 1)
            out["online"] = True
            return out

        if not (s.router_user and s.router_password):
            out["latency_ms"] = round(tcp_probe(r.host, r.port, s.socks), 1)
            out["online"] = True
            out["error"] = "router API credentials not configured — reachability only"
            return out

        import time
        t0 = time.monotonic()
        with RouterOSApi(r.host, r.port, s.router_user, s.router_password, s.socks) as api:
            out["latency_ms"] = round((time.monotonic() - t0) * 1000, 1)
            out["online"] = True
            ident = api.print("/system/identity/print")
            out["identity"] = ident[0].get("name") if ident else None
            res = api.print("/system/resource/print")
            if res:
                x = res[0]
                out.update(version=x.get("version"), board=x.get("board-name"), uptime=x.get("uptime"),
                           cpu_load=_int(x.get("cpu-load")), mem_free=_int(x.get("free-memory")),
                           mem_total=_int(x.get("total-memory")), hdd_free=_int(x.get("free-hdd-space")),
                           hdd_total=_int(x.get("total-hdd-space")))
            for key, cmd in (("hotspot_active", "/ip/hotspot/active/print"),):
                try:
                    out[key] = api.print(cmd, count_only=True)
                except RouterOSError as e:
                    out.setdefault("warnings", []).append(f"{cmd}: {e}")
            if r.um in ("v6", "v7"):
                base = "/tool/user-manager" if r.um == "v6" else "/user-manager"
                for key, cmd in (("um_users", f"{base}/user/print"), ("um_sessions", f"{base}/session/print")):
                    try:
                        out[key] = api.print(cmd, count_only=True)
                    except RouterOSError as e:
                        out.setdefault("warnings", []).append(f"{cmd}: {e}")
    except Exception as e:  # network / auth / protocol errors
        out["online"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _sync_alert(db, router_id: str, kind: str, active: bool, level: str, message: str) -> None:
    open_alert = db.scalar(select(Alert).where(Alert.router_id == router_id, Alert.kind == kind,
                                               Alert.closed_at.is_(None)))
    if active and not open_alert:
        db.add(Alert(router_id=router_id, kind=kind, level=level, message=message))
    elif not active and open_alert:
        open_alert.closed_at = utcnow()


def store(db, r: RouterDef, res: dict) -> None:
    now = utcnow()
    row = db.get(Router, r.id)
    if row is None:
        row = Router(id=r.id, name=r.name, method=r.method)
        db.add(row)
    row.name, row.method, row.last_check = r.name, r.method, now
    if res["online"]:
        row.online, row.fail_count, row.last_seen = True, 0, now
    else:
        row.fail_count = (row.fail_count or 0) + 1
        if row.fail_count >= OFFLINE_AFTER_FAILS:
            row.online = False
    row.last_error = res.get("error") or ("; ".join(res["warnings"]) if res.get("warnings") else None)
    db.flush()

    fields = {k: res.get(k) for k in ("latency_ms", "identity", "version", "board", "uptime", "cpu_load",
                                      "mem_free", "mem_total", "hdd_free", "hdd_total",
                                      "hotspot_active", "um_users", "um_sessions")}
    db.add(Sample(router_id=r.id, ts=now, online=res["online"], **fields))

    _sync_alert(db, r.id, "offline", row.fail_count >= OFFLINE_AFTER_FAILS, "critical",
                f"{r.name}: لا يستجيب")
    cpu = res.get("cpu_load")
    _sync_alert(db, r.id, "cpu", cpu is not None and cpu >= CPU_WARN, "warning",
                f"{r.name}: المعالج {cpu}%")
    free, total = res.get("hdd_free"), res.get("hdd_total")
    low = bool(free is not None and total and free * 100 / total < STORAGE_WARN_PCT)
    _sync_alert(db, r.id, "storage", low, "warning",
                f"{r.name}: مساحة التخزين أقل من {STORAGE_WARN_PCT}%")


def collect_all(SessionLocal, s: Settings, pool: ThreadPoolExecutor) -> None:
    results = dict(zip([r.id for r in s.routers], pool.map(lambda r: collect_one(r, s), s.routers)))
    with SessionLocal() as db:
        for r in s.routers:
            store(db, r, results[r.id])
        db.commit()


def prune(SessionLocal, s: Settings) -> None:
    cutoff = utcnow() - timedelta(days=s.history_days)
    with SessionLocal() as db:
        db.execute(delete(Sample).where(Sample.ts < cutoff))
        db.commit()


async def run_forever(SessionLocal, s: Settings) -> None:
    pool = ThreadPoolExecutor(max_workers=max(2, len(s.routers)))
    loop = asyncio.get_running_loop()
    n = 0
    while True:
        try:
            await loop.run_in_executor(None, collect_all, SessionLocal, s, pool)
            n += 1
            if n % 60 == 0:
                await loop.run_in_executor(None, prune, SessionLocal, s)
        except Exception:
            log.exception("collection cycle failed")
        await asyncio.sleep(s.collect_interval)
