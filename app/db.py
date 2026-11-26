from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey,
                        Integer, String, Text, create_engine, inspect, text)
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
    role: Mapped[str] = mapped_column(String(16), default="owner")  # owner | staff | viewer
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Router(Base):
    __tablename__ = "routers"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(8))
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subnet: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    mem_free: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mem_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hdd_free: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hdd_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hotspot_active: Mapped[int | None] = mapped_column(Integer, nullable=True)
    um_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    um_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rx_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tx_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class RouterSnapshot(Base):
    __tablename__ = "router_snapshots"
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id"), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    interfaces_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    vlans_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    addresses_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotspot_active_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    um_profiles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    um_users_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    speed_label: Mapped[str] = mapped_column(String(64), default="")
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    price_iqd: Mapped[int] = mapped_column(Integer, default=0)
    router_scope: Mapped[str] = mapped_column(String(64), default="all")
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128))
    phone: Mapped[str] = mapped_column(String(32), default="")
    shop_unit: Mapped[str] = mapped_column(String(128), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"), index=True)
    router_id: Mapped[str] = mapped_column(String(64), default="")
    voucher_code: Mapped[str] = mapped_column(String(64), default="", index=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price_iqd: Mapped[int] = mapped_column(Integer, default=0)
    paid_iqd: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="active")
    notes: Mapped[str] = mapped_column(Text, default="")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), index=True)
    amount_iqd: Mapped[int] = mapped_column(Integer)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    method: Mapped[str] = mapped_column(String(32), default="cash")
    note: Mapped[str] = mapped_column(Text, default="")


class VoucherBatch(Base):
    __tablename__ = "voucher_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_code: Mapped[str] = mapped_column(String(32), unique=True)
    router_id: Mapped[str] = mapped_column(String(64), index=True)
    um_version: Mapped[str] = mapped_column(String(8), default="local")
    profile_name: Mapped[str] = mapped_column(String(100))
    count: Mapped[int] = mapped_column(Integer)
    price_iqd: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="draft")  # draft | pushed | partial | failed
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")


class VoucherCard(Base):
    __tablename__ = "voucher_cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("voucher_batches.id"), index=True)
    router_id: Mapped[str] = mapped_column(String(64), index=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    password: Mapped[str] = mapped_column(String(64))
    profile_name: Mapped[str] = mapped_column(String(100))
    price_iqd: Mapped[int] = mapped_column(Integer, default=0)
    pushed_to_router: Mapped[bool] = mapped_column(Boolean, default=False)
    router_item_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sold: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeLog(Base):
    __tablename__ = "change_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    op_id: Mapped[str] = mapped_column(String(32), unique=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    router_id: Mapped[str] = mapped_column(String(64), index=True)
    operator: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    proposal: Mapped[str] = mapped_column(Text)
    approval_record: Mapped[str] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(32))  # success | failed | blocked
    detail: Mapped[str] = mapped_column(Text, default="")
    rollback_hint: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NetworkDevice(Base):
    __tablename__ = "network_devices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    device_type: Mapped[str] = mapped_column(String(32))  # router | switch | ap
    ip_address: Mapped[str] = mapped_column(String(64))
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    vendor: Mapped[str] = mapped_column(String(64), default="MikroTik")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="online")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    op_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id"), index=True)
    target_subsystem: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    before_state_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_change_json: Mapped[str] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16), default="medium")  # low | medium | high
    customer_impact: Mapped[str] = mapped_column(Text, default="")
    rollback_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")  # pending | approved | rejected | executed | rolled_back | failed
    requested_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id"), index=True)
    approved_by: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    operator_note: Mapped[str] = mapped_column(Text, default="")
    approval_token: Mapped[str] = mapped_column(String(128))
    client_ip: Mapped[str] = mapped_column(String(64), default="")


class RollbackRecord(Base):
    __tablename__ = "rollback_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id"), index=True)
    executed_by: Mapped[str] = mapped_column(String(64))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(24))  # success | failed
    execution_log: Mapped[str] = mapped_column(Text, default="")


class Backup(Base):
    __tablename__ = "backups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    router_id: Mapped[str] = mapped_column(ForeignKey("routers.id"), index=True)
    backup_type: Mapped[str] = mapped_column(String(32), default="pre_change")  # pre_change | scheduled | manual
    filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notes: Mapped[str] = mapped_column(Text, default="")


def _migrate_existing_schema(engine) -> None:
    insp = inspect(engine)
    additions = {
        "users": [("active", "BOOLEAN DEFAULT TRUE")],
        "routers": [
            ("vlan_id", "INTEGER"),
            ("subnet", "VARCHAR(64)"),
            ("note", "TEXT"),
        ],
        "samples": [
            ("rx_bytes", "BIGINT"),
            ("tx_bytes", "BIGINT"),
        ],
    }
    with engine.begin() as conn:
        for table, cols in additions.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col_name, col_type in cols:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))


def make_session_factory(url: str):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    _migrate_existing_schema(engine)
    return sessionmaker(engine, expire_on_commit=False)
