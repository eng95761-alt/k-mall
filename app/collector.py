"""Periodic read-only collection from the mall routers.

- method "api": RouterOS API through the tunnel (identity, resources, hotspot
  active count, User Manager counts, and periodic read-only snapshots).
- method "umweb": Fast TCP reachability every cycle + gentle low-frequency
  User Manager v6 Echo2 web scrape (respecting RB2011 CPU).
- method "tcp": reachability + latency only.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from .config import RouterDef, Settings
from .db import Alert, Router, RouterSnapshot, Sample, Setting, utcnow
from .net import open_tcp, tcp_probe
from .routeros import RouterOSApi, RouterOSError
from .um_web import read_um_web

log = logging.getLogger("kmall.collector")

DEFAULT_OFFLINE_AFTER_FAILS = 2
DEFAULT_CPU_WARN = 90
DEFAULT_STORAGE_WARN_PCT = 10
SNAPSHOT_EVERY_CYCLES = 5

_UMWEB_CACHE: dict[str, tuple[float, dict]] = {}
_DYNAMIC_ROUTER_IPS: dict[str, str] = {}
_SUBNET_POOLS: dict[str, str] = {
    "km222-rb3011": "172.17.15.",
    "km222-l009": "172.17.25.",
}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_routeros_dt(val: str | None) -> datetime | None:
    s = (val or "").strip()
    if not s or s.lower() == "not set":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%b/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _read_thresholds(db) -> tuple[int, int, int]:
    rows = {s.key: s.value for s in db.scalars(select(Setting)).all()}
    cpu_warn = _int(rows.get("cpu_warn")) or DEFAULT_CPU_WARN
    storage_warn = _int(rows.get("storage_warn_pct")) or DEFAULT_STORAGE_WARN_PCT
    offline_fails = _int(rows.get("offline_after_fails")) or DEFAULT_OFFLINE_AFTER_FAILS
    return (
        max(10, min(cpu_warn, 100)),
        max(1, min(storage_warn, 90)),
        max(1, min(offline_fails, 20)),
    )


def _socks_alive(socks: tuple[str, int] | None) -> bool:
    if socks is None:
        return True
    try:
        with socket.create_connection(socks, timeout=2.0):
            return True
    except OSError:
        return False


def _connect_api_with_fallback(r: RouterDef, s: Settings) -> tuple[RouterOSApi, float, str]:
    # Candidates list: cached dynamic IP first, then primary host, then alt_hosts
    dyn = _DYNAMIC_ROUTER_IPS.get(r.id)
    ordered_hosts = []
    if dyn:
        ordered_hosts.append(dyn)
    if r.host not in ordered_hosts:
        ordered_hosts.append(r.host)
    for h in (r.alt_hosts or []):
        if h not in ordered_hosts:
            ordered_hosts.append(h)

    last_err = None
    for h in ordered_hosts:
        t0 = time.monotonic()
        try:
            api = RouterOSApi(h, r.port, s.router_user, s.router_password, s.socks, timeout=3.0)
            _DYNAMIC_ROUTER_IPS[r.id] = h
            return api, round((time.monotonic() - t0) * 1000, 1), h
        except Exception as e:
            last_err = e

    # If all configured/cached hosts failed, try fast parallel discovery in known dynamic subnet pool
    pool_prefix = _SUBNET_POOLS.get(r.id)
    if pool_prefix:
        candidate_ips = [f"{pool_prefix}{i}" for i in range(1, 15) if f"{pool_prefix}{i}" not in ordered_hosts]
        def _quick_probe(ip: str) -> str | None:
            try:
                sock = open_tcp(ip, r.port, s.socks, timeout=1.5)
                sock.close()
                return ip
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=8) as ex:
            responsive = [ip for ip in ex.map(_quick_probe, candidate_ips) if ip]

        for ip in responsive:
            t0 = time.monotonic()
            try:
                api = RouterOSApi(ip, r.port, s.router_user, s.router_password, s.socks, timeout=3.0)
                _DYNAMIC_ROUTER_IPS[r.id] = ip
                log.info(f"Auto-discovered dynamic PPPoE IP for {r.id}: {ip}")
                return api, round((time.monotonic() - t0) * 1000, 1), ip
            except Exception as e:
                last_err = e

    raise last_err


def _fetch_api_snapshot(api: RouterOSApi, r: RouterDef, out: dict) -> dict:
    snap = {}
    try:
        ifaces = api.print(
            "/interface/print",
            proplist=["name", "type", "running", "disabled", "rx-byte", "tx-byte", "mac-address"],
            max_rows=200,
        )
        snap["interfaces"] = ifaces
        out["rx_bytes"] = sum(_int(i.get("rx-byte")) or 0 for i in ifaces if i.get("type") == "ether")
        out["tx_bytes"] = sum(_int(i.get("tx-byte")) or 0 for i in ifaces if i.get("type") == "ether")
    except RouterOSError as e:
        out.setdefault("warnings", []).append(f"/interface/print: {e}")

    for key, cmd, props, limit in (
        ("vlans", "/interface/vlan/print", ["name", "vlan-id", "interface", "disabled", "running"], 100),
        ("addresses", "/ip/address/print", ["address", "network", "interface", "disabled"], 100),
        ("hotspot_active", "/ip/hotspot/active/print",
         ["user", "address", "mac-address", "uptime", "bytes-in", "bytes-out", "server"], 500),
    ):
        try:
            snap[key] = api.print(cmd, proplist=props, max_rows=limit)
        except RouterOSError as e:
            out.setdefault("warnings", []).append(f"{cmd}: {e}")

    active_names = {h.get("user") for h in snap.get("hotspot_active", []) if h.get("user")}

    if r.um == "v6":
        try:
            snap["um_profiles"] = api.print(
                "/tool/user-manager/profile/print",
                proplist=["name", "validity", "price", "name-for-users", "starts-at"],
                max_rows=100,
            )
        except RouterOSError as e:
            out.setdefault("warnings", []).append(f"/tool/user-manager/profile/print: {e}")
        try:
            users = api.print(
                "/tool/user-manager/user/print",
                proplist=[".id", "username", "actual-profile", "disabled", "active",
                          "uptime-used", "till-time", "last-seen", "comment"],
                max_rows=2000,
            )
            now = utcnow()
            for u in users:
                dt_till = parse_routeros_dt(u.get("till-time"))
                u["expired"] = bool(
                    dt_till and dt_till < now
                    and u.get("active") != "true"
                    and u.get("username") not in active_names
                )
            snap["um_users"] = users
        except RouterOSError as e:
            out.setdefault("warnings", []).append(f"/tool/user-manager/user/print: {e}")

    elif r.um == "v7":
        try:
            snap["um_profiles"] = api.print(
                "/user-manager/profile/print",
                proplist=["name", "validity", "price", "starts-when", "name-for-users"],
                max_rows=100,
            )
        except RouterOSError as e:
            out.setdefault("warnings", []).append(f"/user-manager/profile/print: {e}")
        up_map: dict[str, dict] = {}
        try:
            ups = api.print(
                "/user-manager/user-profile/print",
                proplist=["user", "profile", "state", "end-time"],
                max_rows=3000,
            )
            for up in ups:
                uname = up.get("user")
                if uname:
                    up_map[uname] = up
        except RouterOSError as e:
            out.setdefault("warnings", []).append(f"/user-manager/user-profile/print: {e}")
        try:
            users = api.print(
                "/user-manager/user/print",
                proplist=[".id", "name", "group", "disabled", "comment"],
                max_rows=2000,
            )
            now = utcnow()
            for u in users:
                uname = u.get("name", "")
                up = up_map.get(uname, {})
                state = up.get("state", "")
                end_t = up.get("end-time", "")
                dt_end = parse_routeros_dt(end_t)
                u["actual-profile"] = up.get("profile") or u.get("group") or ""
                u["end-time"] = end_t
                u["state"] = state
                u["expired"] = bool(
                    (state == "used" or (dt_end and dt_end < now))
                    and uname not in active_names
                    and state != "running-active"
                )
            snap["um_users"] = users
        except RouterOSError as e:
            out.setdefault("warnings", []).append(f"/user-manager/user/print: {e}")

    return snap


def collect_one(r: RouterDef, s: Settings, fetch_snapshot: bool = False, full_umweb: bool = False) -> dict:
    """Runs in a worker thread. Never raises; returns a result dict."""
    out = {"online": False, "latency_ms": None, "error": None, "snapshot": None}
    try:
        if r.method == "tcp":
            out["latency_ms"] = round(tcp_probe(r.host, r.port, s.socks), 1)
            out["online"] = True
            return out

        if r.method == "umweb":
            target_host = r.host
            lat = None
            try:
                lat = round(tcp_probe(r.host, r.port, s.socks), 1)
            except Exception:
                for alt in (r.alt_hosts or []):
                    try:
                        lat = round(tcp_probe(alt, r.port, s.socks), 1)
                        target_host = alt
                        break
                    except Exception:
                        pass
            if lat is None:
                out["online"] = False
                out["error"] = "TCP probe failed"
                return out
            out["latency_ms"] = lat
            out["online"] = True
            if not (s.router_user and s.router_password):
                out["error"] = "credentials not configured — reachability only"
                return out
            now_m = time.monotonic()
            cached = _UMWEB_CACHE.get(r.id)
            if not full_umweb and cached and (now_m - cached[0]) < max(60, r.um_interval):
                out["hotspot_active"] = cached[1].get("hotspot_active")
                out["um_users"] = cached[1].get("um_users")
                out["um_sessions"] = cached[1].get("total_sessions") or cached[1].get("um_sessions")
                return out
            try:
                um_res = read_um_web(
                    target_host, r.port, s.router_user, s.router_password, s.socks,
                    timeout=35.0, full_sync=full_umweb,
                )
                _UMWEB_CACHE[r.id] = (now_m, um_res)
                out["hotspot_active"] = um_res.get("hotspot_active")
                out["um_users"] = um_res.get("um_users")
                out["um_sessions"] = um_res.get("total_sessions") or um_res.get("um_sessions")
                snap = {}
                if um_res.get("um_profiles"):
                    snap["um_profiles"] = um_res["um_profiles"]
                if um_res.get("hotspot_active_rows") is not None:
                    snap["hotspot_active"] = um_res["hotspot_active_rows"]
                if um_res.get("um_users_preview"):
                    snap["um_users"] = um_res["um_users_preview"]
                if um_res.get("db_info"):
                    snap["addresses"] = [{"address": k, "interface": v, "disabled": "false"} for k, v in um_res["db_info"].items()]
                if snap:
                    out["snapshot"] = snap
            except Exception as e:
                if cached:
                    out["hotspot_active"] = cached[1].get("hotspot_active")
                    out["um_users"] = cached[1].get("um_users")
                    out["um_sessions"] = cached[1].get("total_sessions") or cached[1].get("um_sessions")
                out.setdefault("warnings", []).append(f"umweb: {type(e).__name__}: {e}")
            return out

        if not (s.router_user and s.router_password):
            out["latency_ms"] = round(tcp_probe(r.host, r.port, s.socks), 1)
            out["online"] = True
            out["error"] = "router API credentials not configured — reachability only"
            return out

        api, lat_ms, used_host = _connect_api_with_fallback(r, s)
        with api:
            out["latency_ms"] = lat_ms
            out["online"] = True
            if used_host != r.host:
                out.setdefault("warnings", []).append(f"متصل عبر العنوان البديل {used_host}")

            ident = api.print("/system/identity/print", max_rows=5)
            out["identity"] = ident[0].get("name") if ident else None

            res = api.print("/system/resource/print", max_rows=5)
            if res:
                x = res[0]
                out.update(
                    version=x.get("version"),
                    board=x.get("board-name"),
                    uptime=x.get("uptime"),
                    cpu_load=_int(x.get("cpu-load")),
                    mem_free=_int(x.get("free-memory")),
                    mem_total=_int(x.get("total-memory")),
                    hdd_free=_int(x.get("free-hdd-space")),
                    hdd_total=_int(x.get("total-hdd-space")),
                )

            try:
                out["hotspot_active"] = api.print("/ip/hotspot/active/print", count_only=True, max_rows=5)
            except RouterOSError as e:
                out.setdefault("warnings", []).append(f"/ip/hotspot/active/print: {e}")

            if r.um in ("v6", "v7"):
                base = "/tool/user-manager" if r.um == "v6" else "/user-manager"
                for key, cmd in (("um_users", f"{base}/user/print"), ("um_sessions", f"{base}/session/print")):
                    try:
                        out[key] = api.print(cmd, count_only=True, max_rows=5)
                    except RouterOSError as e:
                        out.setdefault("warnings", []).append(f"{cmd}: {e}")

            if fetch_snapshot:
                out["snapshot"] = _fetch_api_snapshot(api, r, out)
    except Exception as e:
        out["online"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _sync_alert(db, router_id: str, kind: str, active: bool, level: str, message: str) -> None:
    open_alert = db.scalar(
        select(Alert).where(Alert.router_id == router_id, Alert.kind == kind, Alert.closed_at.is_(None))
    )
    if active and not open_alert:
        db.add(Alert(router_id=router_id, kind=kind, level=level, message=message))
    elif not active and open_alert:
        open_alert.closed_at = utcnow()


def store(db, r: RouterDef, res: dict, thresholds: tuple[int, int, int] | None = None) -> None:
    cpu_warn, storage_warn_pct, offline_after_fails = thresholds or (
        DEFAULT_CPU_WARN, DEFAULT_STORAGE_WARN_PCT, DEFAULT_OFFLINE_AFTER_FAILS
    )
    now = utcnow()
    row = db.get(Router, r.id)
    if row is None:
        row = Router(id=r.id, name=r.name, method=r.method, vlan_id=r.vlan_id, subnet=r.subnet or None, note=r.note or None)
        db.add(row)
    row.name = r.name
    row.method = r.method
    row.vlan_id = r.vlan_id if r.vlan_id is not None else row.vlan_id
    row.subnet = r.subnet or row.subnet
    row.note = r.note or row.note
    row.last_check = now

    if res["online"]:
        row.online, row.fail_count, row.last_seen = True, 0, now
    else:
        row.fail_count = (row.fail_count or 0) + 1
        if row.fail_count >= offline_after_fails:
            row.online = False
    row.last_error = res.get("error") or ("; ".join(res["warnings"]) if res.get("warnings") else None)
    db.flush()

    fields = {
        k: res.get(k)
        for k in (
            "latency_ms", "identity", "version", "board", "uptime", "cpu_load",
            "mem_free", "mem_total", "hdd_free", "hdd_total",
            "hotspot_active", "um_users", "um_sessions", "rx_bytes", "tx_bytes",
        )
    }
    db.add(Sample(router_id=r.id, ts=now, online=res["online"], **fields))

    snap_data = res.get("snapshot")
    if snap_data is not None:
        snap = db.get(RouterSnapshot, r.id)
        if snap is None:
            snap = RouterSnapshot(router_id=r.id)
            db.add(snap)
        snap.updated_at = now
        if "interfaces" in snap_data:
            snap.interfaces_json = json.dumps(snap_data.get("interfaces", []), ensure_ascii=False)
        if "vlans" in snap_data:
            snap.vlans_json = json.dumps(snap_data.get("vlans", []), ensure_ascii=False)
        if "addresses" in snap_data:
            snap.addresses_json = json.dumps(snap_data.get("addresses", []), ensure_ascii=False)
        if "hotspot_active" in snap_data:
            snap.hotspot_active_json = json.dumps(snap_data.get("hotspot_active", []), ensure_ascii=False)
        if "um_profiles" in snap_data:
            snap.um_profiles_json = json.dumps(snap_data.get("um_profiles", []), ensure_ascii=False)
        if "um_users" in snap_data:
            snap.um_users_json = json.dumps(snap_data.get("um_users", []), ensure_ascii=False)

    _sync_alert(db, r.id, "offline", row.fail_count >= offline_after_fails, "critical", f"{r.name}: لا يستجيب")
    cpu = res.get("cpu_load")
    _sync_alert(db, r.id, "cpu", cpu is not None and cpu >= cpu_warn, "warning", f"{r.name}: المعالج {cpu}%")
    free, total = res.get("hdd_free"), res.get("hdd_total")
    low = bool(free is not None and total and free * 100 / total < storage_warn_pct)
    _sync_alert(db, r.id, "storage", low, "warning", f"{r.name}: مساحة التخزين أقل من {storage_warn_pct}%")


def collect_all(SessionLocal, s: Settings, pool: ThreadPoolExecutor, fetch_snapshot: bool = False) -> None:
    if s.socks and not _socks_alive(s.socks):
        log.warning("SOCKS tunnel proxy %s:%s unreachable", s.socks[0], s.socks[1])
    with SessionLocal() as db:
        thresholds = _read_thresholds(db)
        missing_snap = {
            r.id for r in s.routers
            if r.method == "api" and db.get(RouterSnapshot, r.id) is None
        }
    results = dict(
        zip(
            [r.id for r in s.routers],
            pool.map(lambda r: collect_one(r, s, fetch_snapshot or (r.id in missing_snap)), s.routers),
        )
    )
    with SessionLocal() as db:
        for r in s.routers:
            store(db, r, results[r.id], thresholds=thresholds)
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
    try:
        if s.socks:
            await asyncio.sleep(3.5)
        while True:
            try:
                take_snap = (n % SNAPSHOT_EVERY_CYCLES == 0)
                await loop.run_in_executor(None, collect_all, SessionLocal, s, pool, take_snap)
                n += 1
                if n % 60 == 0:
                    await loop.run_in_executor(None, prune, SessionLocal, s)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("collection cycle failed")
            await asyncio.sleep(s.collect_interval)
    finally:
        pool.shutdown(wait=False)
