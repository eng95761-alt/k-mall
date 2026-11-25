from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .collector import run_forever
from .db import Alert, AuditLog, Router, Sample, User, make_session_factory, utcnow
from .security import SECURITY_HEADERS, LoginLimiter, hash_password, verify_password

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kmall")

settings = config.load()
SessionLocal = make_session_factory(settings.database_url)
limiter = LoginLimiter()
STATIC = Path(__file__).parent / "static"


def bootstrap_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        if not (settings.admin_username and settings.admin_password):
            log.warning("No users yet and ADMIN_USERNAME/ADMIN_PASSWORD not set — nobody can log in.")
            return
        if len(settings.admin_password) < 10:
            raise RuntimeError("ADMIN_PASSWORD must be at least 10 characters")
        db.add(User(username=settings.admin_username, pw_hash=hash_password(settings.admin_password), role="owner"))
        db.commit()
        log.info("Created owner account %s", settings.admin_username)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap_admin()
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
    # CSRF: state-changing calls must carry our custom header (not sendable cross-site without CORS).
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.headers.get("x-kmall") != "1":
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def audit(username: str | None, action: str, detail: str | None, ip: str) -> None:
    with SessionLocal() as db:
        db.add(AuditLog(username=username, action=action, detail=detail, ip=ip))
        db.commit()


def current_user(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "not logged in")
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
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == body.username))
    if not user or not verify_password(body.password, user.pw_hash):
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
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


# ---------------- data (read-only) ----------------
def utc(dt: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; all stored times are UTC — make that explicit for the browser."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def sample_dict(s: Sample | None) -> dict | None:
    if s is None:
        return None
    d = {k: getattr(s, k) for k in ("ts", "online", "latency_ms", "identity", "version", "board", "uptime",
                                     "cpu_load", "mem_free", "mem_total", "hdd_free", "hdd_total",
                                     "hotspot_active", "um_users", "um_sessions")}
    d["ts"] = utc(d["ts"])
    return d


@app.get("/api/overview")
def overview(user: dict = Depends(current_user)):
    order = {r.id: i for i, r in enumerate(settings.routers)}
    defs = {r.id: r for r in settings.routers}
    with SessionLocal() as db:
        routers = db.scalars(select(Router)).all()
        out = []
        for r in sorted(routers, key=lambda r: order.get(r.id, 999)):
            if r.id not in defs:
                continue
            last = db.scalar(select(Sample).where(Sample.router_id == r.id).order_by(Sample.ts.desc()).limit(1))
            last_full = db.scalar(select(Sample).where(Sample.router_id == r.id, Sample.online.is_(True),
                                                       Sample.cpu_load.is_not(None))
                                  .order_by(Sample.ts.desc()).limit(1))
            out.append({"id": r.id, "name": r.name, "method": r.method, "note": defs[r.id].note,
                        "online": r.online, "last_seen": utc(r.last_seen), "last_check": utc(r.last_check),
                        "last_error": r.last_error, "latest": sample_dict(last),
                        "latest_full": sample_dict(last_full)})
        alerts = db.scalars(select(Alert).where(Alert.closed_at.is_(None)).order_by(Alert.opened_at.desc())).all()
    totals = {
        "routers": len(out),
        "online": sum(1 for r in out if r["online"]),
        "hotspot_active": sum((r["latest"] or {}).get("hotspot_active") or 0 for r in out),
    }
    return {"now": utcnow(), "interval": settings.collect_interval, "routers": out, "totals": totals,
            "alerts": [{"router_id": a.router_id, "kind": a.kind, "level": a.level, "message": a.message,
                        "opened_at": utc(a.opened_at)} for a in alerts]}


@app.get("/api/routers/{router_id}/history")
def history(router_id: str, hours: int = 24, user: dict = Depends(current_user)):
    hours = max(1, min(hours, 24 * 30))
    since = utcnow() - timedelta(hours=hours)
    with SessionLocal() as db:
        rows = db.scalars(select(Sample).where(Sample.router_id == router_id, Sample.ts >= since)
                          .order_by(Sample.ts)).all()
    return [sample_dict(s) for s in rows]


@app.get("/api/alerts")
def alerts(limit: int = 100, user: dict = Depends(current_user)):
    with SessionLocal() as db:
        rows = db.scalars(select(Alert).order_by(Alert.opened_at.desc()).limit(min(limit, 500))).all()
    return [{"router_id": a.router_id, "kind": a.kind, "level": a.level, "message": a.message,
             "opened_at": utc(a.opened_at), "closed_at": utc(a.closed_at)} for a in rows]


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---------------- frontend ----------------
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
