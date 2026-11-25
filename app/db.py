from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String,
                        Text, create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    pw_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="owner")  # owner | staff
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Router(Base):
    __tablename__ = "routers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(8))
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Sample(Base):
    __tablename__ = "samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    online: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    identity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    board: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uptime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cpu_load: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mem_free: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mem_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hdd_free: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hdd_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hotspot_active: Mapped[int | None] = mapped_column(Integer, nullable=True)
    um_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    um_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))          # offline | cpu | storage
    level: Mapped[str] = mapped_column(String(16))         # critical | warning
    message: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


def make_session_factory(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)
