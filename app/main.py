from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .collector import (DEFAULT_CPU_WARN, DEFAULT_OFFLINE_AFTER_FAILS,
                        DEFAULT_STORAGE_WARN_PCT, _UMWEB_CACHE, collect_one,
                        parse_routeros_dt, run_forever, store)
from .db import (Alert, AuditLog, ChangeLog, Customer, Payment, Plan, Router,
                 RouterSnapshot, Sample, Setting, Subscription, User,
                 VoucherBatch, VoucherCard, make_session_factory, utcnow)
from .routeros import RouterOSError, WritesDisabled
from .security import (SECURITY_HEADERS, LoginLimiter, hash_password,
                       verify_password)
from .vouchers import (build_proposal_summary, generate_batch_pairs,
                       inspect_old_closed_sessions, push_vouchers_to_router,
                       remove_expired_items_safely)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kmall")

settings = config.load()
SessionLocal = make_session_factory(settings.database_url)
limiter = LoginLimiter()
STATIC = Path(__file__).parent / "static"


def bootstrap_defaults() -> None:
    with SessionLocal() as db:
        for k, v in (
            ("cpu_warn", str(DEFAULT_CPU_WARN)),
            ("storage_warn_pct", str(DEFAULT_STORAGE_WARN_PCT)),
            ("offline_after_fails", str(DEFAULT_OFFLINE_AFTER_FAILS)),
        ):
            if db.get(Setting, k) is None:
                db.add(Setting(key=k, value=v))
        for r in settings.routers:
            row = db.get(Router, r.id)
            if row is None:
                db.add(Router(id=r.id, name=r.name, method=r.method, vlan_id=r.vlan_id,
                              subnet=r.subnet or None, note=r.note or None))
            else:
                row.name = r.name
                row.method = r.method
                if r.vlan_id is not None:
                    row.vlan_id = r.vlan_id
                if r.subnet:
                    row.subnet = r.subnet
                if r.note:
                    row.note = r.note
        if settings.admin_password:
            if len(settings.admin_password) < 10:
                raise RuntimeError("ADMIN_PASSWORD must be at least 10 characters")
            target_usernames = {settings.admin_username, "owner", "admin"} if settings.admin_username else {"owner", "admin"}
            for u_name in target_usernames:
                u_row = db.scalar(select(User).where(func.lower(User.username) == u_name.lower()))
                if u_row:
                    if not verify_password(settings.admin_password, u_row.pw_hash):
                        u_row.pw_hash = hash_password(settings.admin_password)
                        u_row.active = True
                        log.info("Synchronized %s password from ADMIN_PASSWORD env var", u_name)
                else:
                    db.add(User(username=u_name, pw_hash=hash_password(settings.admin_password), role="owner", active=True))
                    log.info("Created account %s with synchronized admin password", u_name)
        elif not db.scalar(select(func.count()).select_from(User)):
            log.warning("No users yet and ADMIN_USERNAME/ADMIN_PASSWORD not set — nobody can log in.")
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_defaults()
    task = None
    if settings.routers:
        task = asyncio.create_task(run_forever(SessionLocal, settings))
    else:
        log.warning("ROUTERS_JSON is empty — collector not started.")
    yield
    if task:
        task.cancel()


app = FastAPI(title="K-Mall Network", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="kmall_session",
                   max_age=12 * 3600, same_site="strict", https_only=settings.https_only)


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get("x-kmall") != "1":
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if settings.https_only:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def client_ip(request: Request) -> str:
    # Behind a single reverse proxy (Render), the proxy appends the real client IP at the end.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        parts = [p.strip() for p in fwd.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "?"


def audit(username: str | None, action: str, detail: str | None, ip: str) -> None:
    with SessionLocal() as db:
        db.add(AuditLog(username=username, action=action, detail=detail, ip=ip))
        db.commit()


def current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "not logged in")
    with SessionLocal() as db:
        row = db.get(User, user["id"])
        if not row or not row.active:
            request.session.clear()
            raise HTTPException(401, "account inactive")
        return {"id": row.id, "username": row.username, "role": row.role}


def require_owner(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "owner":
        raise HTTPException(403, "owner role required")
    return user


def require_staff(user: dict = Depends(current_user)) -> dict:
    if user["role"] not in ("owner", "staff"):
        raise HTTPException(403, "write role required")
    return user


# ---------------- auth ----------------
class LoginIn(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    ip = client_ip(request)
    if limiter.blocked(ip):
        raise HTTPException(429, "محاولات كثيرة، حاول بعد 15 دقيقة")
    clean_username = body.username.strip()
    clean_password = body.password.strip()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.username) == clean_username.lower()))
        if not user and clean_username.lower() in ("admin", "owner"):
            user = db.scalar(select(User).where(User.role == "owner"))

    valid_pw = False
    if user and user.active:
        valid_pw = verify_password(body.password, user.pw_hash) or verify_password(clean_password, user.pw_hash)

    if not user or not user.active or not valid_pw:
        limiter.fail(ip)
        audit(body.username, "login_failed", None, ip)
        raise HTTPException(401, "اسم المستخدم أو كلمة المرور غير صحيحة")
    limiter.reset(ip)
    request.session.clear()
    request.session["user"] = {"id": user.id, "username": user.username, "role": user.role}
    audit(user.username, "login", None, ip)
    return {"username": user.username, "role": user.role}


@app.post("/api/logout")
def logout(request: Request):
    user = request.session.get("user")
    if user:
        audit(user.get("username"), "logout", None, client_ip(request))
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


# ---------------- helpers ----------------
def utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def sample_dict(s: Sample | None) -> dict | None:
    if s is None:
        return None
    d = {
        k: getattr(s, k)
        for k in (
            "ts", "online", "latency_ms", "identity", "version", "board", "uptime",
            "cpu_load", "mem_free", "mem_total", "hdd_free", "hdd_total",
            "hotspot_active", "um_users", "um_sessions", "rx_bytes", "tx_bytes",
        )
    }
    d["ts"] = utc(d["ts"])
    return d


def _csv_response(filename: str, headers: list[str], rows: list[list]) -> Response:
    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM for Microsoft Excel Arabic compatibility
    w = csv.writer(buf)
    w.writerow(headers)
    w.writerows(rows)
    return Response(
        content=buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
    )


# ---------------- monitoring (read-only) ----------------
@app.get("/api/overview")
def overview(user: dict = Depends(current_user)):
    order = {r.id: i for i, r in enumerate(settings.routers)}
    defs = {r.id: r for r in settings.routers}
    with SessionLocal() as db:
        routers = db.scalars(select(Router)).all()
        out = []
        for r in sorted(routers, key=lambda x: order.get(x.id, 999)):
            if r.id not in defs:
                continue
            last = db.scalar(select(Sample).where(Sample.router_id == r.id).order_by(Sample.ts.desc()).limit(1))
            last_full = db.scalar(
                select(Sample).where(
                    Sample.router_id == r.id,
                    Sample.online.is_(True),
                    (Sample.cpu_load.is_not(None)) | (Sample.um_users.is_not(None)) | (Sample.hotspot_active.is_not(None)),
                ).order_by(Sample.ts.desc()).limit(1)
            )
            out.append({
                "id": r.id, "name": r.name, "method": r.method, "host": defs[r.id].host,
                "port": defs[r.id].port, "um": defs[r.id].um, "vlan_id": r.vlan_id,
                "subnet": r.subnet, "note": defs[r.id].note or r.note,
                "can_write_vouchers": bool(defs[r.id].method == "api" and defs[r.id].um in ("v6", "v7")),
                "online": r.online, "last_seen": utc(r.last_seen), "last_check": utc(r.last_check),
                "last_error": r.last_error, "latest": sample_dict(last), "latest_full": sample_dict(last_full),
            })
        alerts = db.scalars(select(Alert).where(Alert.closed_at.is_(None)).order_by(Alert.opened_at.desc())).all()
        subs = db.scalars(select(Subscription)).all()
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        sales_today = db.scalar(select(func.coalesce(func.sum(Payment.amount_iqd), 0)).where(Payment.paid_at >= today_start)) or 0
        outstanding = sum(max(0, s.price_iqd - s.paid_iqd) for s in subs)
        active_subs = sum(1 for s in subs if s.status == "active")

    totals = {
        "routers": len(out),
        "online": sum(1 for r in out if r["online"]),
        "hotspot_active": sum(
            ((r["latest"] or {}).get("hotspot_active") if (r["latest"] or {}).get("hotspot_active") is not None
             else ((r["latest_full"] or {}).get("hotspot_active") or 0))
            for r in out
        ),
        "um_users": sum(
            ((r["latest"] or {}).get("um_users") if (r["latest"] or {}).get("um_users") is not None
             else ((r["latest_full"] or {}).get("um_users") or 0))
            for r in out
        ),
        "sales_today_iqd": int(sales_today),
        "outstanding_iqd": int(outstanding),
        "active_subs": active_subs,
    }
    return {
        "now": utcnow(), "interval": settings.collect_interval,
        "allow_router_writes": settings.allow_router_writes,
        "routers": out, "totals": totals,
        "alerts": [
            {"id": a.id, "router_id": a.router_id, "kind": a.kind, "level": a.level, "message": a.message, "opened_at": utc(a.opened_at)}
            for a in alerts
        ],
    }


@app.get("/api/routers/{router_id}/history")
def history(router_id: str, hours: int = 24, user: dict = Depends(current_user)):
    hours = max(1, min(hours, 24 * 30))
    since = utcnow() - timedelta(hours=hours)
    with SessionLocal() as db:
        rows = db.scalars(
            select(Sample).where(Sample.router_id == router_id, Sample.ts >= since).order_by(Sample.ts)
        ).all()
    return [sample_dict(s) for s in rows]


@app.get("/api/routers/{router_id}/snapshot")
def router_snapshot(router_id: str, user: dict = Depends(current_user)):
    with SessionLocal() as db:
        snap = db.get(RouterSnapshot, router_id)
        if not snap:
            return {"router_id": router_id, "updated_at": None, "interfaces": [], "vlans": [],
                    "addresses": [], "hotspot_active": [], "um_profiles": [], "um_users": []}
        return {
            "router_id": router_id,
            "updated_at": utc(snap.updated_at),
            "interfaces": json.loads(snap.interfaces_json or "[]"),
            "vlans": json.loads(snap.vlans_json or "[]"),
            "addresses": json.loads(snap.addresses_json or "[]"),
            "hotspot_active": json.loads(snap.hotspot_active_json or "[]"),
            "um_profiles": json.loads(snap.um_profiles_json or "[]"),
            "um_users": json.loads(snap.um_users_json or "[]"),
        }


def parse_routeros_duration(s: str | None) -> timedelta | None:
    if not s:
        return None
    w = int(m.group(1)) if (m := re.search(r"(\d+)w", s)) else 0
    d = int(m.group(1)) if (m := re.search(r"(\d+)d", s)) else 0
    h = int(m.group(1)) if (m := re.search(r"(\d+)h", s)) else 0
    m_val = int(m.group(1)) if (m := re.search(r"(\d+)m(?!s)", s)) else 0
    sec = int(m.group(1)) if (m := re.search(r"(\d+)s", s)) else 0
    return timedelta(weeks=w, days=d, hours=h, minutes=m_val, seconds=sec)


@app.get("/api/hotspot/active")
def list_active_hotspot_clients(router_id: str | None = None, q: str = "", user: dict = Depends(current_user)):
    defs = {r.id: r for r in settings.routers}
    order = {r.id: i for i, r in enumerate(settings.routers)}
    q_low = q.strip().lower()
    now = utcnow()
    results = []

    with SessionLocal() as db:
        snaps = db.scalars(select(RouterSnapshot)).all()
        for snap in snaps:
            rid = snap.router_id
            if rid not in defs:
                continue
            if router_id and rid != router_id:
                continue
            rdef = defs[rid]
            actives = json.loads(snap.hotspot_active_json or "[]")
            um_users = json.loads(snap.um_users_json or "[]")
            user_map = {}
            for u in um_users:
                uname = u.get("username") or u.get("name")
                if uname:
                    user_map[uname] = u

            for a in actives:
                uname = a.get("user")
                if not uname:
                    continue
                ip_addr = a.get("address") or "—"
                mac_addr = a.get("mac-address") or "—"
                if q_low and (q_low not in uname.lower() and q_low not in ip_addr.lower() and q_low not in mac_addr.lower() and q_low not in rdef.name.lower()):
                    continue

                u_info = user_map.get(uname, {})
                uptime_str = a.get("uptime") or ""
                dur = parse_routeros_duration(uptime_str)
                calc_start = (now - dur) if dur else None
                from_time_raw = a.get("from-time") or u_info.get("last-seen")
                act_dt = parse_routeros_dt(from_time_raw) or calc_start
                activated_str = act_dt.strftime("%Y-%m-%d %H:%M") if act_dt else (uptime_str or "—")

                till_raw = a.get("till-time") or u_info.get("till-time") or u_info.get("end-time")
                exp_dt = parse_routeros_dt(till_raw)
                expires_str = exp_dt.strftime("%Y-%m-%d %H:%M") if exp_dt else (till_raw or "—")

                time_left_str = "—"
                is_expired = False
                if exp_dt:
                    diff = exp_dt - now
                    if diff.total_seconds() > 0:
                        days = diff.days
                        hrs = int(diff.seconds // 3600)
                        mins = int((diff.seconds % 3600) // 60)
                        if days > 0:
                            time_left_str = f"{days} يوم و {hrs} ساعة"
                        elif hrs > 0:
                            time_left_str = f"{hrs} ساعة و {mins} دقيقة"
                        else:
                            time_left_str = f"{mins} دقيقة"
                    else:
                        time_left_str = "منتهي الصلاحية"
                        is_expired = True

                prof = u_info.get("actual-profile") or u_info.get("profile") or "Hotspot"

                # Parse bytes
                bin_raw = a.get("bytes-in") or 0
                bout_raw = a.get("bytes-out") or 0
                bin_val = int(bin_raw) if str(bin_raw).isdigit() else 0
                bout_val = int(bout_raw) if str(bout_raw).isdigit() else 0

                results.append({
                    "username": uname,
                    "router_id": rid,
                    "router_name": rdef.name,
                    "vlan_id": rdef.vlan_id,
                    "ip_address": ip_addr,
                    "mac_address": mac_addr,
                    "server": a.get("server") or "hotspot1",
                    "profile": prof,
                    "uptime": uptime_str,
                    "activated_at": activated_str,
                    "expires_at": expires_str,
                    "time_left": time_left_str,
                    "is_expired": is_expired,
                    "bytes_in": bin_val,
                    "bytes_out": bout_val,
                })

    results.sort(key=lambda x: (order.get(x["router_id"], 999), x["username"]))
    return {"count": len(results), "clients": results}


@app.get("/api/cards")
def list_cards(router_id: str | None = None, q: str = "", status: str = "all", user: dict = Depends(current_user)):
    q_low = q.strip().lower()
    items = []
    with SessionLocal() as db:
        routers = {r.id: r for r in db.scalars(select(Router)).all()}
        snaps = db.scalars(select(RouterSnapshot)).all()
        for snap in snaps:
            if router_id and snap.router_id != router_id:
                continue
            rname = routers[snap.router_id].name if snap.router_id in routers else snap.router_id
            for u in json.loads(snap.um_users_json or "[]"):
                uname = u.get("username") or u.get("name") or ""
                prof = u.get("actual-profile") or u.get("group") or ""
                comment = u.get("comment") or ""
                expired = bool(u.get("expired"))
                disabled = u.get("disabled") in ("true", True, "yes")
                if status == "expired" and not expired:
                    continue
                if status == "active" and (expired or disabled):
                    continue
                if q_low and q_low not in uname.lower() and q_low not in prof.lower() and q_low not in comment.lower():
                    continue
                items.append({
                    "id": u.get(".id", ""),
                    "router_id": snap.router_id,
                    "router_name": rname,
                    "username": uname,
                    "profile": prof,
                    "disabled": disabled,
                    "expired": expired,
                    "state": u.get("state", ""),
                    "start_time": u.get("start-time", ""),
                    "end_time": u.get("end-time", ""),
                    "till_time": u.get("till-time", ""),
                    "uptime_used": u.get("uptime-used") or "",
                    "last_seen": u.get("last-seen") or "",
                    "comment": comment,
                    "updated_at": utc(snap.updated_at),
                })
    return {"count": len(items), "items": items[:1000]}


@app.post("/api/routers/{router_id}/sync")
def sync_router_now(router_id: str, request: Request, user: dict = Depends(require_staff)):
    defs = {r.id: r for r in settings.routers}
    rdef = defs.get(router_id)
    if not rdef:
        raise HTTPException(404, "الراوتر غير موجود")
    res = collect_one(rdef, settings, fetch_snapshot=True, full_umweb=True)
    with SessionLocal() as db:
        store(db, rdef, res)
        db.commit()
        snap = db.get(RouterSnapshot, router_id)
        users_cnt = len(json.loads(snap.um_users_json or "[]")) if snap else 0
        profs_cnt = len(json.loads(snap.um_profiles_json or "[]")) if snap else 0
    audit(user["username"], "router_sync", f"{router_id} users={users_cnt} profs={profs_cnt}", client_ip(request))
    return {"ok": res["online"], "users": users_cnt, "profiles": profs_cnt, "error": res.get("error")}


@app.post("/api/routers/{router_id}/test")
def test_router_now(router_id: str, request: Request, user: dict = Depends(current_user)):
    defs = {r.id: r for r in settings.routers}
    rdef = defs.get(router_id)
    if not rdef:
        raise HTTPException(404, "الراوتر غير موجود")
    t0 = time.monotonic()
    res = collect_one(rdef, settings, fetch_snapshot=False)
    lat = round((time.monotonic() - t0) * 1000, 1)
    with SessionLocal() as db:
        store(db, rdef, res)
        db.commit()
    audit(user["username"], "router_test", f"{router_id} online={res['online']} lat={lat}ms", client_ip(request))
    return {
        "ok": res["online"],
        "latency_ms": res.get("latency_ms", lat),
        "router_id": router_id,
        "error": res.get("error"),
        "cpu": res.get("cpu_load"),
        "hotspot_active": res.get("hotspot_active", 0),
    }


class CleanupExecuteIn(BaseModel):
    approved: bool
    confirm_router_id: str = Field(min_length=1, max_length=64)
    action: str = Field(pattern="^(remove_expired_users|remove_old_sessions|rebuild_db)$")
    ids: list[str] = Field(min_length=1, max_length=100)
    min_age_days: int = Field(default=0, ge=0, le=3650)


@app.get("/api/cleanup/{router_id}/preview")
def cleanup_preview(router_id: str, min_age_days: int = 0, user: dict = Depends(current_user)):
    defs = {r.id: r for r in settings.routers}
    rdef = defs.get(router_id)
    if not rdef:
        raise HTTPException(404, "الراوتر غير موجود")
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=min_age_days)) if min_age_days > 0 else now
    with SessionLocal() as db:
        snap = db.get(RouterSnapshot, router_id)
        last = db.scalar(select(Sample).where(Sample.router_id == router_id).order_by(Sample.ts.desc()).limit(1))
        users = json.loads(snap.um_users_json or "[]") if snap else []
        expired_users = []
        for u in users:
            if not u.get("expired"):
                continue
            if min_age_days > 0:
                t_str = u.get("till-time") or u.get("end-time")
                dt = parse_routeros_dt(t_str)
                if dt and dt > cutoff:
                    continue
            expired_users.append({
                "id": u.get(".id", ""),
                "username": u.get("username") or u.get("name") or "",
                "profile": u.get("actual-profile") or u.get("group") or "",
                "end_time": u.get("end-time", ""),
                "till_time": u.get("till-time", ""),
                "last_seen": u.get("last-seen", ""),
            })
        db_info = json.loads(snap.addresses_json or "[]") if snap else []
    old_sessions = []
    if rdef.method == "api" and rdef.um in ("v6", "v7"):
        try:
            old_sessions = inspect_old_closed_sessions(rdef, settings, min_age_days=min_age_days)
        except Exception:
            old_sessions = []
    total_sess = last.um_sessions if (last and last.um_sessions) else None
    if total_sess is None and rdef.method == "umweb":
        cached = _UMWEB_CACHE.get(router_id)
        if cached:
            total_sess = cached[1].get("total_sessions") or cached[1].get("um_sessions")
    active_sess = (last.hotspot_active if (last and last.hotspot_active is not None) else 0)
    web_url = f"http://{rdef.host}:{rdef.port}/userman" if rdef.method == "umweb" else None
    return {
        "router_id": router_id,
        "router_name": rdef.name,
        "method": rdef.method,
        "can_auto_clean": True,
        "allow_router_writes": settings.allow_router_writes,
        "total_cached_users": len(users),
        "expired_users": expired_users[:200],
        "expired_count": len(expired_users),
        "total_sessions": total_sess,
        "active_sessions": active_sess,
        "old_closed_sessions": old_sessions,
        "db_info": db_info,
        "web_url": web_url,
    }


@app.post("/api/cleanup/{router_id}/execute")
def cleanup_execute(router_id: str, body: CleanupExecuteIn, request: Request, user: dict = Depends(require_owner)):
    if not body.approved or body.confirm_router_id != router_id:
        raise HTTPException(400, "تأكيد وموافقة المالك الصريحة مطلوبة")
    defs = {r.id: r for r in settings.routers}
    rdef = defs.get(router_id)
    if not rdef:
        raise HTTPException(404, "الراوتر غير موجود")
    op_id = f"OP-{utcnow().strftime('%Y%m%d-%H%M%S')}-CLN-{secrets.token_hex(2)}"
    proposal = f"تنظيف آمن ({body.action}) لعدد {len(body.ids)} سجل منتهي على {rdef.name}"
    rollback = "استرجاع نسخة User Manager المحفوظة في backups/ عند الحاجة"

    with SessionLocal() as db:
        if not settings.allow_router_writes:
            db.add(ChangeLog(
                op_id=op_id, router_id=router_id, operator=user["username"],
                action=body.action, proposal=proposal,
                approval_record=f"owner:{user['username']} (blocked by ALLOW_ROUTER_WRITES=false)",
                result="blocked", detail=f"ids={len(body.ids)}", rollback_hint=rollback,
            ))
            db.commit()
            raise HTTPException(403, "الحذف والتعديل معطل افتراضياً (ALLOW_ROUTER_WRITES=false) حمايةً للمشتركين.")
        if rdef.method == "umweb" and body.action == "rebuild_db":
            from .um_web import rebuild_um_web_db
            res = rebuild_um_web_db(rdef.host, rdef.port, settings.router_user, settings.router_password, settings.socks)
            db.add(ChangeLog(
                op_id=op_id, router_id=router_id, operator=user["username"],
                action=body.action, proposal=proposal,
                approval_record=f"owner:{user['username']} explicit UI confirmation",
                result="success" if res.get("ok") else "failed",
                detail=res.get("detail", ""), rollback_hint=rollback,
            ))
            db.commit()
            return {"ok": True, "op_id": op_id, "detail": res.get("detail", "تمت صيانة وإعادة بناء قاعدة البيانات بنجاح")}
        try:
            removed = remove_expired_items_safely(rdef, settings, body.action, body.ids, min_age_days=body.min_age_days)
            db.add(ChangeLog(
                op_id=op_id, router_id=router_id, operator=user["username"],
                action=body.action, proposal=proposal,
                approval_record=f"owner:{user['username']} explicit UI confirmation",
                result="success", detail=f"removed={removed}", rollback_hint=rollback,
            ))
            db.commit()
            audit(user["username"], body.action, f"{op_id} removed={removed}", client_ip(request))
            return {"ok": True, "op_id": op_id, "removed": removed, "detail": f"تم بنجاح تفريغ {removed} سجل منتهي دون أي مساس بالمشتركين النشطين."}
        except (RouterOSError, WritesDisabled, OSError) as e:
            db.add(ChangeLog(
                op_id=op_id, router_id=router_id, operator=user["username"],
                action=body.action, proposal=proposal,
                approval_record=f"owner:{user['username']} explicit UI confirmation",
                result="failed", detail=str(e), rollback_hint=rollback,
            ))
            db.commit()
            raise HTTPException(502, f"توقف التنظيف بأمان: {e}")


@app.get("/api/alerts")
def alerts(limit: int = 100, active_only: bool = True, user: dict = Depends(current_user)):
    with SessionLocal() as db:
        q = select(Alert)
        if active_only:
            q = q.where(Alert.closed_at.is_(None))
        rows = db.scalars(q.order_by(Alert.opened_at.desc()).limit(min(limit, 500))).all()
    return [
        {"id": a.id, "router_id": a.router_id, "kind": a.kind, "level": a.level, "message": a.message,
         "opened_at": utc(a.opened_at), "closed_at": utc(a.closed_at)}
        for a in rows
    ]


@app.post("/api/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, request: Request, user: dict = Depends(require_staff)):
    with SessionLocal() as db:
        al = db.get(Alert, alert_id)
        if not al:
            raise HTTPException(404, "التنبيه غير موجود")
        al.closed_at = utcnow()
        db.commit()
    audit(user["username"], "alert_ack", f"id={alert_id}", client_ip(request))
    return {"ok": True, "id": alert_id}


# ---------------- settings & RBAC users (owner only) ----------------
class ThresholdsIn(BaseModel):
    cpu_warn: int = Field(ge=10, le=100)
    storage_warn_pct: int = Field(ge=1, le=90)
    offline_after_fails: int = Field(ge=1, le=20)


@app.get("/api/settings")
def get_settings(user: dict = Depends(current_user)):
    with SessionLocal() as db:
        rows = {s.key: s.value for s in db.scalars(select(Setting)).all()}
    return {
        "cpu_warn": int(rows.get("cpu_warn", DEFAULT_CPU_WARN)),
        "storage_warn_pct": int(rows.get("storage_warn_pct", DEFAULT_STORAGE_WARN_PCT)),
        "offline_after_fails": int(rows.get("offline_after_fails", DEFAULT_OFFLINE_AFTER_FAILS)),
    }


@app.put("/api/settings")
def update_settings(body: ThresholdsIn, request: Request, user: dict = Depends(require_owner)):
    with SessionLocal() as db:
        for k, v in (
            ("cpu_warn", str(body.cpu_warn)),
            ("storage_warn_pct", str(body.storage_warn_pct)),
            ("offline_after_fails", str(body.offline_after_fails)),
        ):
            row = db.get(Setting, k)
            if row:
                row.value = v
            else:
                db.add(Setting(key=k, value=v))
        db.commit()
    audit(user["username"], "settings_update", json.dumps(body.model_dump()), client_ip(request))
    return body.model_dump()


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    role: str = Field(pattern="^(owner|staff|viewer)$")


class UserToggleIn(BaseModel):
    active: bool


@app.get("/api/users")
def list_users(user: dict = Depends(require_owner)):
    with SessionLocal() as db:
        rows = db.scalars(select(User).order_by(User.id)).all()
    return [{"id": u.id, "username": u.username, "role": u.role, "active": u.active, "created_at": utc(u.created_at)} for u in rows]


@app.post("/api/users")
def create_user(body: UserCreateIn, request: Request, user: dict = Depends(require_owner)):
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == body.username)):
            raise HTTPException(409, "اسم المستخدم موجود مسبقاً")
        u = User(username=body.username, pw_hash=hash_password(body.password), role=body.role, active=True)
        db.add(u)
        db.commit()
        db.refresh(u)
    audit(user["username"], "user_create", f"{u.username} ({u.role})", client_ip(request))
    return {"id": u.id, "username": u.username, "role": u.role, "active": u.active}


@app.patch("/api/users/{user_id}")
def toggle_user(user_id: int, body: UserToggleIn, request: Request, user: dict = Depends(require_owner)):
    if user_id == user["id"] and not body.active:
        raise HTTPException(400, "لا يمكن تعطيل حسابك الحالي")
    with SessionLocal() as db:
        u = db.get(User, user_id)
        if not u:
            raise HTTPException(404, "المستخدم غير موجود")
        u.active = body.active
        db.commit()
    audit(user["username"], "user_toggle", f"{u.username} active={body.active}", client_ip(request))
    return {"id": u.id, "active": u.active}


@app.get("/api/audit")
def list_audit(limit: int = 100, user: dict = Depends(require_owner)):
    with SessionLocal() as db:
        rows = db.scalars(select(AuditLog).order_by(AuditLog.ts.desc()).limit(min(limit, 300))).all()
    return [{"ts": utc(a.ts), "username": a.username, "action": a.action, "detail": a.detail, "ip": a.ip} for a in rows]


# ---------------- commercial layer (platform DB only — never touches routers) ----------------
class PlanIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    speed_label: str = Field(default="", max_length=64)
    duration_days: int = Field(ge=1, le=3650)
    price_iqd: int = Field(ge=0, le=100_000_000)
    router_scope: str = Field(default="all", max_length=64)
    notes: str = Field(default="", max_length=500)


class CustomerIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=128)
    phone: str = Field(default="", max_length=32)
    shop_unit: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=500)


class SubscriptionIn(BaseModel):
    customer_id: int
    plan_id: int
    router_id: str = Field(default="", max_length=64)
    voucher_code: str = Field(default="", max_length=64)
    paid_iqd: int = Field(default=0, ge=0, le=100_000_000)
    notes: str = Field(default="", max_length=500)


class PaymentIn(BaseModel):
    amount_iqd: int = Field(gt=0, le=100_000_000)
    method: str = Field(default="cash", max_length=32)
    note: str = Field(default="", max_length=300)


@app.get("/api/plans")
def get_plans(user: dict = Depends(current_user)):
    with SessionLocal() as db:
        rows = db.scalars(select(Plan).order_by(Plan.id)).all()
    return [{"id": p.id, "name": p.name, "speed_label": p.speed_label, "duration_days": p.duration_days,
             "price_iqd": p.price_iqd, "router_scope": p.router_scope, "notes": p.notes, "active": p.active} for p in rows]


@app.post("/api/plans")
def create_plan(body: PlanIn, request: Request, user: dict = Depends(require_staff)):
    with SessionLocal() as db:
        if db.scalar(select(Plan).where(Plan.name == body.name)):
            raise HTTPException(409, "اسم الباقة موجود مسبقاً")
        p = Plan(**body.model_dump())
        db.add(p)
        db.commit()
        db.refresh(p)
    audit(user["username"], "plan_create", p.name, client_ip(request))
    return {"id": p.id, "name": p.name}


@app.get("/api/customers")
def get_customers(q: str = "", user: dict = Depends(current_user)):
    q_low = q.strip().lower()
    with SessionLocal() as db:
        rows = db.scalars(select(Customer).order_by(Customer.id.desc())).all()
    out = []
    for c in rows:
        if q_low and q_low not in c.full_name.lower() and q_low not in c.phone.lower() and q_low not in c.shop_unit.lower():
            continue
        out.append({"id": c.id, "full_name": c.full_name, "phone": c.phone, "shop_unit": c.shop_unit,
                    "notes": c.notes, "created_at": utc(c.created_at)})
    return out


@app.post("/api/customers")
def create_customer(body: CustomerIn, request: Request, user: dict = Depends(require_staff)):
    with SessionLocal() as db:
        c = Customer(**body.model_dump())
        db.add(c)
        db.commit()
        db.refresh(c)
    audit(user["username"], "customer_create", c.full_name, client_ip(request))
    return {"id": c.id, "full_name": c.full_name}


@app.get("/api/subscriptions")
def get_subscriptions(user: dict = Depends(current_user)):
    with SessionLocal() as db:
        subs = db.scalars(select(Subscription).order_by(Subscription.id.desc())).all()
        custs = {c.id: c for c in db.scalars(select(Customer)).all()}
        plans = {p.id: p for p in db.scalars(select(Plan)).all()}
        now = utcnow()
        out = []
        for s in subs:
            exp = utc(s.expires_at)
            effective_status = "expired" if (s.status == "active" and exp and exp < now) else s.status
            c = custs.get(s.customer_id)
            p = plans.get(s.plan_id)
            out.append({
                "id": s.id,
                "customer_id": s.customer_id,
                "customer_name": c.full_name if c else "—",
                "shop_unit": c.shop_unit if c else "",
                "plan_id": s.plan_id,
                "plan_name": p.name if p else "—",
                "router_id": s.router_id,
                "voucher_code": s.voucher_code,
                "activated_at": utc(s.activated_at),
                "expires_at": exp,
                "price_iqd": s.price_iqd,
                "paid_iqd": s.paid_iqd,
                "balance_iqd": max(0, s.price_iqd - s.paid_iqd),
                "status": effective_status,
                "notes": s.notes,
            })
        return out


@app.post("/api/subscriptions")
def create_subscription(body: SubscriptionIn, request: Request, user: dict = Depends(require_staff)):
    with SessionLocal() as db:
        cust = db.get(Customer, body.customer_id)
        plan = db.get(Plan, body.plan_id)
        if not cust or not plan:
            raise HTTPException(404, "الزبون أو الباقة غير موجودة")
        now = utcnow()
        sub = Subscription(
            customer_id=cust.id,
            plan_id=plan.id,
            router_id=body.router_id,
            voucher_code=body.voucher_code,
            activated_at=now,
            expires_at=now + timedelta(days=plan.duration_days),
            price_iqd=plan.price_iqd,
            paid_iqd=min(body.paid_iqd, plan.price_iqd) if plan.price_iqd else body.paid_iqd,
            status="active",
            notes=body.notes,
        )
        db.add(sub)
        db.flush()
        if sub.paid_iqd > 0:
            db.add(Payment(subscription_id=sub.id, amount_iqd=sub.paid_iqd, method="cash", note="دفعة تفعيل"))
        db.commit()
        db.refresh(sub)
    audit(user["username"], "subscription_create", f"sub#{sub.id} cust={cust.full_name} plan={plan.name}", client_ip(request))
    return {"id": sub.id}


@app.post("/api/subscriptions/{sub_id}/payments")
def add_payment(sub_id: int, body: PaymentIn, request: Request, user: dict = Depends(require_staff)):
    with SessionLocal() as db:
        sub = db.get(Subscription, sub_id)
        if not sub:
            raise HTTPException(404, "الاشتراك غير موجود")
        pay = Payment(subscription_id=sub.id, amount_iqd=body.amount_iqd, method=body.method, note=body.note)
        sub.paid_iqd = (sub.paid_iqd or 0) + body.amount_iqd
        db.add(pay)
        db.commit()
    audit(user["username"], "payment_create", f"sub#{sub_id} +{body.amount_iqd}", client_ip(request))
    return {"ok": True, "paid_iqd": sub.paid_iqd, "balance_iqd": max(0, sub.price_iqd - sub.paid_iqd)}


# ---------------- vouchers & controlled change management ----------------
class VoucherBatchIn(BaseModel):
    router_id: str = Field(min_length=1, max_length=64)
    profile_name: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=1, le=100)
    prefix: str = Field(default="KM", max_length=12)
    user_len: int = Field(default=6, ge=4, le=12)
    pass_len: int = Field(default=6, ge=4, le=12)
    digits_only: bool = False
    price_iqd: int = Field(default=0, ge=0, le=100_000_000)
    notes: str = Field(default="", max_length=300)


class BatchPushIn(BaseModel):
    approved: bool
    confirm_router_id: str = Field(min_length=1, max_length=64)


@app.get("/api/vouchers/profiles/{router_id}")
def voucher_profiles(router_id: str, user: dict = Depends(current_user)):
    defs = {r.id: r for r in settings.routers}
    if router_id not in defs:
        raise HTTPException(404, "الراوتر غير موجود")
    rdef = defs[router_id]
    with SessionLocal() as db:
        snap = db.get(RouterSnapshot, router_id)
        raw_profiles = json.loads(snap.um_profiles_json or "[]") if snap else []

    out = []
    for p in raw_profiles:
        name = p.get("name") or p.get(".id") or ""
        if not name:
            continue
        price_val = 0
        for pk in ("price", "cost", "validity-cost"):
            try:
                v = int(float(p.get(pk) or 0))
                if v > 0:
                    price_val = v
                    break
            except (ValueError, TypeError):
                pass
        validity = p.get("validity") or p.get("uptime-limit") or p.get("duration") or ""
        rate_limit = p.get("rate-limit") or p.get("rate_limit") or ""
        out.append({
            "name": name,
            "price": price_val,
            "validity": validity,
            "rate_limit": rate_limit,
            "raw": p,
        })

    # Default fallback profiles for the mall hotspot
    if not out:
        out = [
            {"name": "5000 IQD (30 Days)", "price": 5000, "validity": "30d", "rate_limit": "10M/10M"},
            {"name": "10000 IQD (60 Days)", "price": 10000, "validity": "60d", "rate_limit": "15M/15M"},
            {"name": "3000 IQD (7 Days)", "price": 3000, "validity": "7d", "rate_limit": "10M/10M"},
            {"name": "1000 IQD (1 Day)", "price": 1000, "validity": "1d", "rate_limit": "8M/8M"},
            {"name": "VIP Unlimited", "price": 25000, "validity": "30d", "rate_limit": "25M/25M"},
        ]

    return {"router_id": router_id, "um_version": rdef.um or "v6", "profiles": out}


@app.get("/api/vouchers/batches")
def list_voucher_batches(user: dict = Depends(current_user)):
    with SessionLocal() as db:
        batches = db.scalars(select(VoucherBatch).order_by(VoucherBatch.id.desc()).limit(100)).all()
    return {
        "allow_router_writes": settings.allow_router_writes,
        "batches": [
            {
                "id": b.id, "batch_code": b.batch_code, "router_id": b.router_id,
                "um_version": b.um_version, "profile_name": b.profile_name, "count": b.count,
                "price_iqd": b.price_iqd, "status": b.status, "created_by": b.created_by,
                "created_at": utc(b.created_at), "notes": b.notes,
            }
            for b in batches
        ],
    }


@app.get("/api/vouchers/batches/{batch_id}")
def get_voucher_batch(batch_id: int, user: dict = Depends(current_user)):
    defs = {r.id: r for r in settings.routers}
    with SessionLocal() as db:
        b = db.get(VoucherBatch, batch_id)
        if not b:
            raise HTTPException(404, "الدفعة غير موجودة")
        cards = db.scalars(select(VoucherCard).where(VoucherCard.batch_id == batch_id).order_by(VoucherCard.id)).all()
    rdef = defs.get(b.router_id)
    if rdef:
        proposal, cmd_preview, rollback = build_proposal_summary(rdef, b.count, b.profile_name)
    else:
        proposal, cmd_preview, rollback = ("دفعة محلية", "—", "—")
    return {
        "batch": {
            "id": b.id, "batch_code": b.batch_code, "router_id": b.router_id,
            "um_version": b.um_version, "profile_name": b.profile_name, "count": b.count,
            "price_iqd": b.price_iqd, "status": b.status, "created_by": b.created_by,
            "created_at": utc(b.created_at), "notes": b.notes,
        },
        "proposal": {
            "summary": proposal,
            "commands": cmd_preview,
            "rollback": rollback,
            "can_push": bool(rdef and rdef.method == "api" and rdef.um in ("v6", "v7")),
            "allow_router_writes": settings.allow_router_writes,
        },
        "cards": [
            {
                "id": c.id, "username": c.username, "password": c.password,
                "profile_name": c.profile_name, "price_iqd": c.price_iqd,
                "pushed_to_router": c.pushed_to_router, "sold": c.sold,
            }
            for c in cards
        ],
    }


@app.post("/api/vouchers/batches")
def create_voucher_batch(body: VoucherBatchIn, request: Request, user: dict = Depends(require_staff)):
    defs = {r.id: r for r in settings.routers}
    rdef = defs.get(body.router_id)
    if not rdef:
        raise HTTPException(404, "الراوتر غير موجود")

    with SessionLocal() as db:
        existing = set(db.scalars(select(VoucherCard.username)).all())
        snap = db.get(RouterSnapshot, body.router_id)
        if snap and snap.um_users_json:
            for u in json.loads(snap.um_users_json):
                uname = u.get("username") or u.get("name")
                if uname:
                    existing.add(uname)

        pairs = generate_batch_pairs(
            body.count, prefix=body.prefix, user_len=body.user_len,
            pass_len=body.pass_len, digits_only=body.digits_only, existing_usernames=existing,
        )
        batch_code = f"B{utcnow().strftime('%y%m%d%H%M%S')}-{secrets.token_hex(2)}"
        batch = VoucherBatch(
            batch_code=batch_code, router_id=body.router_id, um_version=rdef.um or "local",
            profile_name=body.profile_name, count=len(pairs), price_iqd=body.price_iqd,
            status="draft", created_by=user["username"], notes=body.notes,
        )
        db.add(batch)
        db.flush()
        for uname, pwd in pairs:
            db.add(VoucherCard(
                batch_id=batch.id, router_id=body.router_id, username=uname,
                password=pwd, profile_name=body.profile_name, price_iqd=body.price_iqd,
            ))
        db.commit()
        db.refresh(batch)

    audit(user["username"], "voucher_batch_create", f"{batch.batch_code} x{batch.count} -> {body.router_id}", client_ip(request))
    return {"id": batch.id, "batch_code": batch.batch_code}


@app.post("/api/vouchers/batches/{batch_id}/push")
def push_voucher_batch(batch_id: int, body: BatchPushIn, request: Request, user: dict = Depends(require_owner)):
    if not body.approved:
        raise HTTPException(400, "يتطلب التنفيذ موافقة صريحة من المالك")
    defs = {r.id: r for r in settings.routers}
    with SessionLocal() as db:
        b = db.get(VoucherBatch, batch_id)
        if not b:
            raise HTTPException(404, "الدفعة غير موجودة")
        if body.confirm_router_id != b.router_id:
            raise HTTPException(400, "معرّف الراوتر المؤكَّد لا يطابق الدفعة")
        rdef = defs.get(b.router_id)
        if not rdef or rdef.method != "api" or rdef.um not in ("v6", "v7"):
            raise HTTPException(400, "هذا الراوتر لا يدعم الدفع الآلي عبر API (قراءة فقط)")

        cards = db.scalars(select(VoucherCard).where(VoucherCard.batch_id == batch_id).order_by(VoucherCard.id)).all()
        proposal, _, rollback = build_proposal_summary(rdef, len(cards), b.profile_name)
        op_id = f"OP-{utcnow().strftime('%Y%m%d-%H%M%S')}-{b.id}-{secrets.token_hex(2)}"

        if not settings.allow_router_writes:
            db.add(ChangeLog(
                op_id=op_id, router_id=b.router_id, operator=user["username"],
                action="push_vouchers", proposal=proposal,
                approval_record=f"owner:{user['username']} (blocked by ALLOW_ROUTER_WRITES=false)",
                result="blocked", detail="ALLOW_ROUTER_WRITES=false", rollback_hint=rollback,
            ))
            db.commit()
            raise HTTPException(403, "الكتابة على الراوترات معطلة افتراضياً (ALLOW_ROUTER_WRITES=false) حمايةً للشبكة. فعّلها في متغيرات البيئة عند الرغبة بالدفع الفعلي.")

        try:
            pushed, _ = push_vouchers_to_router(rdef, settings, cards, b.profile_name, b.batch_code)
            b.status = "pushed" if all(c.pushed_to_router for c in cards) else "partial"
            db.add(ChangeLog(
                op_id=op_id, router_id=b.router_id, operator=user["username"],
                action="push_vouchers", proposal=proposal,
                approval_record=f"owner:{user['username']} explicit UI confirmation",
                result="success", detail=f"pushed={pushed}/{len(cards)}", rollback_hint=rollback,
            ))
            db.commit()
            audit(user["username"], "voucher_batch_push", f"{op_id} pushed={pushed}", client_ip(request))
            return {"ok": True, "op_id": op_id, "pushed": pushed, "status": b.status}
        except (RouterOSError, WritesDisabled, OSError) as e:
            b.status = "partial" if any(c.pushed_to_router for c in cards) else "failed"
            db.add(ChangeLog(
                op_id=op_id, router_id=b.router_id, operator=user["username"],
                action="push_vouchers", proposal=proposal,
                approval_record=f"owner:{user['username']} explicit UI confirmation",
                result="failed", detail=str(e), rollback_hint=rollback,
            ))
            db.commit()
            raise HTTPException(502, f"توقف التنفيذ عند أول خطأ: {e}")


@app.get("/api/changes")
def list_changes(limit: int = 100, user: dict = Depends(current_user)):
    with SessionLocal() as db:
        rows = db.scalars(select(ChangeLog).order_by(ChangeLog.ts.desc()).limit(min(limit, 300))).all()
    return [
        {
            "op_id": c.op_id, "ts": utc(c.ts), "router_id": c.router_id, "operator": c.operator,
            "action": c.action, "proposal": c.proposal, "approval_record": c.approval_record,
            "result": c.result, "detail": c.detail, "rollback_hint": c.rollback_hint,
        }
        for c in rows
    ]


@app.get("/api/reports/batch/{batch_id}.csv")
def export_batch_csv(batch_id: int, request: Request, user: dict = Depends(current_user)):
    with SessionLocal() as db:
        b = db.get(VoucherBatch, batch_id)
        if not b:
            raise HTTPException(404, "الدفعة غير موجودة")
        cards = db.scalars(select(VoucherCard).where(VoucherCard.batch_id == batch_id).order_by(VoucherCard.id)).all()
    audit(user["username"], "export_csv", f"batch={b.batch_code}", client_ip(request))
    return _csv_response(
        f"vouchers-{b.batch_code}.csv",
        ["batch_code", "router_id", "username", "password", "profile", "price_iqd", "pushed_to_router"],
        [[b.batch_code, c.router_id, c.username, c.password, c.profile_name, c.price_iqd, c.pushed_to_router] for c in cards],
    )


# ---------------- CSV exports ----------------
@app.get("/api/reports/samples.csv")
def export_samples_csv(request: Request, hours: int = 24, user: dict = Depends(current_user)):
    hours = max(1, min(hours, 24 * 30))
    since = utcnow() - timedelta(hours=hours)
    with SessionLocal() as db:
        rows = db.scalars(select(Sample).where(Sample.ts >= since).order_by(Sample.ts.desc()).limit(5000)).all()
    audit(user["username"], "export_csv", f"samples hours={hours}", client_ip(request))
    return _csv_response(
        "kmall-samples.csv",
        ["timestamp_utc", "router_id", "online", "latency_ms", "cpu_load", "mem_free", "mem_total",
         "hdd_free", "hdd_total", "hotspot_active", "um_users", "um_sessions"],
        [[utc(s.ts).isoformat(), s.router_id, s.online, s.latency_ms, s.cpu_load, s.mem_free,
          s.mem_total, s.hdd_free, s.hdd_total, s.hotspot_active, s.um_users, s.um_sessions] for s in rows],
    )


@app.get("/api/reports/cards.csv")
def export_cards_csv(request: Request, router_id: str | None = None, user: dict = Depends(current_user)):
    data = list_cards(router_id=router_id, q="", user=user)["items"]
    audit(user["username"], "export_csv", f"cards count={len(data)}", client_ip(request))
    return _csv_response(
        "kmall-cards.csv",
        ["router_id", "router_name", "username", "profile", "disabled", "uptime_used", "last_seen", "comment"],
        [[c["router_id"], c["router_name"], c["username"], c["profile"], c["disabled"],
          c["uptime_used"], c["last_seen"], c["comment"]] for c in data],
    )


@app.get("/api/reports/sales.csv")
def export_sales_csv(request: Request, user: dict = Depends(current_user)):
    subs = get_subscriptions(user=user)
    audit(user["username"], "export_csv", f"sales count={len(subs)}", client_ip(request))
    return _csv_response(
        "kmall-sales.csv",
        ["id", "customer_name", "shop_unit", "plan_name", "router_id", "voucher_code",
         "activated_at", "expires_at", "price_iqd", "paid_iqd", "balance_iqd", "status"],
        [[s["id"], s["customer_name"], s["shop_unit"], s["plan_name"], s["router_id"], s["voucher_code"],
          s["activated_at"].isoformat() if s["activated_at"] else "",
          s["expires_at"].isoformat() if s["expires_at"] else "",
          s["price_iqd"], s["paid_iqd"], s["balance_iqd"], s["status"]] for s in subs],
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------------- frontend ----------------
app.mount("/static", StaticFiles(directory=STATIC), name="static")
if (STATIC / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")


@app.get("/favicon.ico")
def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#0284c7"/><text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" fill="#fff" font-family="sans-serif" font-size="20" font-weight="bold">K</text></svg>'
    return Response(content=svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/favicon.svg")
def favicon_svg():
    fav_file = STATIC / "favicon.svg"
    if fav_file.exists():
        return FileResponse(fav_file, media_type="image/svg+xml")
    return favicon()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})
