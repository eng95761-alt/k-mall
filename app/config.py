"""All settings come from environment variables. Nothing secret lives in code."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class RouterDef:
    id: str
    name: str
    host: str
    method: str                 # "api" = RouterOS API read; "tcp" = reachability only
    port: int                   # API port for "api", probe port for "tcp"
    um: str | None = None       # "v6" | "v7" | None — which User Manager to read
    note: str = ""


@dataclass
class Settings:
    database_url: str
    secret_key: str
    admin_username: str | None
    admin_password: str | None
    router_user: str | None
    router_password: str | None
    socks: tuple[str, int] | None
    routers: list[RouterDef] = field(default_factory=list)
    collect_interval: int = 60
    https_only: bool = True
    history_days: int = 30


def _socks(value: str | None) -> tuple[str, int] | None:
    if not value:
        return None
    host, _, port = value.rpartition(":")
    return host, int(port)


def load() -> Settings:
    db = os.environ.get("DATABASE_URL", "sqlite:///./kmall.db")
    if db.startswith("postgres://"):            # Render style → SQLAlchemy psycopg3
        db = "postgresql+psycopg://" + db[len("postgres://"):]
    elif db.startswith("postgresql://"):
        db = "postgresql+psycopg://" + db[len("postgresql://"):]

    secret = os.environ.get("SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("SECRET_KEY must be set (at least 32 characters)")

    routers = [RouterDef(**r) for r in json.loads(os.environ.get("ROUTERS_JSON", "[]"))]

    return Settings(
        database_url=db,
        secret_key=secret,
        admin_username=os.environ.get("ADMIN_USERNAME"),
        admin_password=os.environ.get("ADMIN_PASSWORD"),
        router_user=os.environ.get("ROUTER_API_USER"),
        router_password=os.environ.get("ROUTER_API_PASSWORD"),
        socks=_socks(os.environ.get("SOCKS_PROXY", "127.0.0.1:25344")),
        routers=routers,
        collect_interval=int(os.environ.get("COLLECT_INTERVAL", "60")),
        https_only=os.environ.get("HTTPS_ONLY", "true").lower() == "true",
        history_days=int(os.environ.get("HISTORY_DAYS", "30")),
    )
