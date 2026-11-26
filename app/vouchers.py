"""Voucher code generation, User Manager write adapters (v6/v7), and safe expired cleanup."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .collector import parse_routeros_dt
from .config import RouterDef, Settings
from .routeros import RouterOSApi, RouterOSError, _attrs

SAFE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
SAFE_DIGITS = "23456789"


def generate_code(length: int, digits_only: bool = False) -> str:
    pool = SAFE_DIGITS if digits_only else SAFE_ALPHABET
    return "".join(secrets.choice(pool) for _ in range(length))


def generate_batch_pairs(
    count: int,
    prefix: str = "",
    user_len: int = 6,
    pass_len: int = 6,
    digits_only: bool = False,
    existing_usernames: Iterable[str] = (),
) -> list[tuple[str, str]]:
    seen = set(existing_usernames)
    out: list[tuple[str, str]] = []
    clean_prefix = "".join(ch for ch in prefix.strip() if ch.isalnum() or ch in ("-", "_"))[:12]
    attempts = 0
    while len(out) < count:
        attempts += 1
        if attempts > count * 20:
            raise ValueError("could not generate enough unique voucher codes")
        uname = f"{clean_prefix}{generate_code(user_len, digits_only=digits_only)}"
        if uname in seen:
            continue
        seen.add(uname)
        pwd = generate_code(pass_len, digits_only=digits_only)
        out.append((uname, pwd))
    return out


def build_proposal_summary(r: RouterDef, count: int, profile_name: str) -> tuple[str, str, str]:
    if r.um == "v6":
        cmd = (
            f"/tool/user-manager/user/add customer=<um-customer> username=<code> password=<pass> + "
            f"/tool/user-manager/user/create-and-activate-profile profile={profile_name}"
        )
        rollback = f"تعطيل أو إزالة الكروت المضافة من قائمة Users في WinBox/User Manager على {r.name}"
    elif r.um == "v7":
        cmd = (
            f"/user-manager/user/add name=<code> password=<pass> + "
            f"/user-manager/user-profile/add user=<code> profile={profile_name}"
        )
        rollback = f"تعطيل أو إزالة الكروت المضافة من قائمة User Manager -> Users على {r.name}"
    else:
        cmd = "لا يدعم الكتابة التلقائية (إنشاء محلي للطباعة فقط)"
        rollback = "إجراء محلي فقط — لا يوجد أي تعديل على الراوتر"
    proposal = (
        f"إنشاء {count} كرت اشتراك على راوتر {r.name} ({r.host}:{r.port}) "
        f"باستخدام باقة '{profile_name}' عبر محول User Manager ({r.um or 'local'})."
    )
    return proposal, cmd, rollback


def _connect_api(r: RouterDef, s: Settings, allow_writes: bool = False) -> RouterOSApi:
    if r.method != "api" or r.um not in ("v6", "v7"):
        raise RouterOSError(f"الراوتر {r.name} لا يدعم API (حالته: {r.method})")
    if not (s.router_user and s.router_password):
        raise RouterOSError("بيانات دخول RouterOS API غير مضبوطة")
    hosts = [r.host] + [h for h in r.alt_hosts if h != r.host]
    last_err = None
    for h in hosts:
        try:
            return RouterOSApi(h, r.port, s.router_user, s.router_password, s.socks, allow_writes=allow_writes)
        except Exception as e:
            last_err = e
    raise last_err


def push_vouchers_to_router(
    r: RouterDef,
    s: Settings,
    cards: list,
    profile_name: str,
    batch_code: str,
) -> tuple[int, str | None]:
    pushed = 0
    with _connect_api(r, s, allow_writes=s.allow_router_writes) as api:
        if r.um == "v6":
            customers = api.print("/tool/user-manager/customer/print", max_rows=20)
            customer = customers[0].get("login", "admin") if customers else "admin"
            for card in cards:
                if card.pushed_to_router:
                    continue
                item_id = api.write_typed("/tool/user-manager/user/add", {
                    "customer": customer,
                    "username": card.username,
                    "password": card.password,
                    "comment": f"kmall:{batch_code}",
                    "disabled": "no",
                })
                api.write_typed("/tool/user-manager/user/create-and-activate-profile", {
                    "numbers": item_id or card.username,
                    "profile": profile_name,
                    "customer": customer,
                })
                card.pushed_to_router = True
                card.router_item_id = item_id
                pushed += 1
        elif r.um == "v7":
            groups = api.print("/user-manager/user/group/print", max_rows=20)
            group_name = groups[0].get("name", "default") if groups else "default"
            for card in cards:
                if card.pushed_to_router:
                    continue
                item_id = api.write_typed("/user-manager/user/add", {
                    "name": card.username,
                    "password": card.password,
                    "group": group_name,
                    "comment": f"kmall:{batch_code}",
                    "disabled": "no",
                })
                api.write_typed("/user-manager/user-profile/add", {
                    "user": card.username,
                    "profile": profile_name,
                })
                card.pushed_to_router = True
                card.router_item_id = item_id
                pushed += 1
    return pushed, None


def inspect_old_closed_sessions(r: RouterDef, s: Settings, min_age_days: int = 0, max_scan: int = 500) -> list[dict]:
    """Read-only bounded scan of oldest closed sessions on API routers without draining huge tables."""
    if r.method != "api" or r.um not in ("v6", "v7"):
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)) if min_age_days > 0 else datetime.now(timezone.utc)
    cmd = "/tool/user-manager/session/print" if r.um == "v6" else "/user-manager/session/print"
    found: list[dict] = []
    with _connect_api(r, s, allow_writes=False) as api:
        api._send_sentence([cmd, "=.proplist=.id,user,from-time,till-time,ended,active"])
        scanned = 0
        while True:
            sent = api._read_sentence()
            if not sent:
                continue
            if sent[0] == "!re":
                scanned += 1
                row = _attrs(sent[1:])
                is_active = row.get("active") == "true"
                t_str = row.get("till-time") or row.get("ended")
                dt = parse_routeros_dt(t_str)
                if not is_active and (dt is None or dt < cutoff):
                    found.append({
                        "id": row.get(".id"),
                        "user": row.get("user", ""),
                        "from_time": row.get("from-time", ""),
                        "till_time": t_str or "",
                    })
                if len(found) >= 100 or scanned >= max_scan:
                    break
            elif sent[0] in ("!done", "!trap", "!fatal"):
                break
    return found


def remove_expired_items_safely(
    r: RouterDef,
    s: Settings,
    action: str,
    ids: list[str],
    min_age_days: int = 0,
) -> int:
    """Safely remove explicitly selected expired users or old closed sessions on API routers."""
    if r.method != "api" or r.um not in ("v6", "v7"):
        raise RouterOSError("التنظيف الآلي عبر API متاح فقط لراوترات RB3011 وL009. لراوترات RB2011 يتم استخدام واجهة الويب.")

    removed = 0
    with _connect_api(r, s, allow_writes=s.allow_router_writes) as api:
        # Always double-check currently active Hotspot users before deleting ANY user
        active_rows = api.print("/ip/hotspot/active/print", proplist=["user"], max_rows=500)
        active_users = {a.get("user") for a in active_rows if a.get("user")}

        target_ids = list(ids)
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=min_age_days)) if min_age_days > 0 else now

        if target_ids == ["all_expired"]:
            target_ids = []
            if action == "remove_expired_users":
                cmd_u = "/tool/user-manager/user/print" if r.um == "v6" else "/user-manager/user/print"
                all_u = api.print(cmd_u, proplist=[".id", "username", "name", "till-time", "end-time", "uptime-used"], max_rows=1000)
                for u in all_u:
                    uname = u.get("username") or u.get("name") or ""
                    if not uname or uname in active_users:
                        continue
                    till_dt = parse_routeros_dt(u.get("till-time", ""))
                    end_dt = parse_routeros_dt(u.get("end-time", ""))
                    if (end_dt and end_dt < cutoff) or (till_dt and till_dt < cutoff):
                        if ".id" in u:
                            target_ids.append(u[".id"])
                    if len(target_ids) >= 100:
                        break
            elif action == "remove_old_sessions":
                closed_sess = inspect_old_closed_sessions(r, s, min_age_days=min_age_days, max_scan=500)
                target_ids = [cs["id"] for cs in closed_sess if cs.get("id")][:100]

        if not target_ids:
            return 0
        if len(target_ids) > 100:
            target_ids = target_ids[:100]

        if action == "remove_expired_users":
            cmd_u = "/tool/user-manager/user/print" if r.um == "v6" else "/user-manager/user/print"
            cmd_rm = "/tool/user-manager/user/remove" if r.um == "v6" else "/user-manager/user/remove"
            current_users = api.print(cmd_u, proplist=[".id", "username", "name"], max_rows=2000)
            id_to_name = {u[".id"]: (u.get("username") or u.get("name") or "") for u in current_users if ".id" in u}
            for item_id in target_ids:
                uname = id_to_name.get(item_id, "")
                if uname and uname in active_users:
                    continue  # Safe skip active subscribers
                try:
                    api.write_typed(cmd_rm, {"numbers": item_id})
                    removed += 1
                except Exception:
                    pass
        elif action == "remove_old_sessions":
            cmd_rm = "/tool/user-manager/session/remove" if r.um == "v6" else "/user-manager/session/remove"
            for item_id in target_ids:
                try:
                    api.write_typed(cmd_rm, {"numbers": item_id})
                    removed += 1
                except Exception:
                    pass
        else:
            raise RouterOSError("إجراء تنظيف غير مدعوم")
    return removed
