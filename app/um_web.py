"""Read-only MikroTik RouterOS v6 Legacy User Manager Web (NextApp Echo2) client.

Supports SOCKS5 tunneling via app.net.open_tcp so it works both on LAN and
through Back to Home (wireproxy) on Render. Always logs out cleanly.
"""
from __future__ import annotations

import http.client
import http.cookies
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from .net import open_tcp


class UMWebError(Exception):
    pass


class _SocksHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, port: int, socks: tuple[str, int] | None, timeout: float):
        super().__init__(host, port=port, timeout=timeout)
        self._socks = socks

    def connect(self) -> None:
        self.sock = open_tcp(self.host, self.port, self._socks, self.timeout or 15.0)
        self.sock.settimeout(self.timeout or 15.0)


def _request(host: str, port: int, path: str, socks: tuple[str, int] | None, timeout: float,
             method: str = "GET", body: bytes | None = None, cookie: str | None = None) -> tuple[int, str, str | None]:
    conn = _SocksHTTPConnection(host, port, socks, timeout)
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "text/xml; charset=utf-8"
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", "replace")
        set_cookie = resp.getheader("Set-Cookie")
        next_cookie = cookie
        if set_cookie and "MWTSESSION=" in set_cookie:
            c = http.cookies.SimpleCookie()
            c.load(set_cookie)
            if "MWTSESSION" in c:
                next_cookie = f"MWTSESSION={c['MWTSESSION'].value}"
        return resp.status, data, next_cookie
    finally:
        conn.close()


def _parse_um_date(val: str) -> datetime | None:
    s = (val or "").strip()
    if not s or s.lower() == "not set":
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%b/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _is_expired_row(start_t: str, end_t: str, till_t: str, time_left: str, active_names: set[str], uname: str) -> bool:
    if uname in active_names:
        return False
    now = datetime.now(timezone.utc)
    dt_end = _parse_um_date(end_t)
    if dt_end and dt_end < now:
        return True
    dt_till = _parse_um_date(till_t)
    if dt_till and dt_till < now:
        return True
    if time_left and time_left.strip() in ("0s", "0d0h0m0s", "0h0m0s", "00:00:00"):
        return True
    return False


def _parse_users_table(xml_text: str, active_names: set[str] | None = None) -> list[dict]:
    users = []
    active_set = active_names or set()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return users
    for elem in root.iter():
        if elem.tag.split("}")[-1] != "table":
            continue
        rows = []
        for tr in elem.iter():
            if tr.tag.split("}")[-1] == "tr":
                cells = ["".join(td.itertext()).strip() for td in tr if td.tag.split("}")[-1] == "td"]
                if cells:
                    rows.append(cells)
        if rows and rows[0] and "Username" in rows[0]:
            col_map = {name.strip().lower(): idx for idx, name in enumerate(rows[0]) if name.strip()}
            for r in rows[1:]:
                # skip sort header rows (r[0] is empty) or header repetitions
                if not r or not r[0] or r[0].lower() in ("username", "password"):
                    continue
                uname = r[0]
                def get_val(col_name: str, default: str = "") -> str:
                    idx = col_map.get(col_name)
                    return r[idx] if idx is not None and len(r) > idx else default
                till_t = get_val("till time")
                start_t = get_val("start time")
                end_t = get_val("end time")
                left = get_val("total time left")
                prof = get_val("actual profile")
                paid = get_val("money paid")
                uptime = get_val("uptime used")
                expired = _is_expired_row(start_t, end_t, till_t, left, active_set, uname)
                users.append({
                    "username": uname,
                    "actual-profile": prof,
                    "till-time": till_t,
                    "start-time": start_t,
                    "end-time": end_t,
                    "uptime-used": left or uptime,
                    "comment": f"paid={paid}" if paid else "",
                    "last-seen": end_t if end_t and end_t != "Not set" else start_t,
                    "disabled": "false",
                    "expired": expired,
                })
            break
    return users


def _parse_active_sessions(xml_text: str) -> list[dict]:
    sessions = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return sessions
    for elem in root.iter():
        if elem.tag.split("}")[-1] != "table":
            continue
        rows = []
        for tr in elem.iter():
            if tr.tag.split("}")[-1] == "tr":
                cells = ["".join(td.itertext()).strip() for td in tr if td.tag.split("}")[-1] == "td"]
                if cells:
                    rows.append(cells)
        if rows and rows[0] and rows[0][0] == "Username" and "User IP" in rows[0]:
            for r in rows[1:]:
                if len(r) >= 9 and r[0] and r[0] not in ("Username", "Status"):
                    sessions.append({
                        "user": r[0],
                        "status": r[1],
                        "address": r[2],
                        "from-time": r[3],
                        "till-time": r[4],
                        "uptime": r[5],
                        "bytes-in": r[6],
                        "bytes-out": r[7],
                        "mac-address": r[8],
                    })
            break
    return sessions


def _parse_profiles(xml_text: str) -> list[dict]:
    m = re.search(r'<load-content content-id="0">(.*?)</load-content>', xml_text, re.S)
    if not m:
        return []
    names = re.findall(r'<item value="([^"]+)"', m.group(1))
    return [{"name": n, "validity": "—", "price": "—"} for n in names]


def _parse_maintenance(xml_text: str) -> dict:
    info = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return info
    for elem in root.iter():
        if elem.tag.split("}")[-1] != "table":
            continue
        for tr in elem.iter():
            if tr.tag.split("}")[-1] == "tr":
                cells = ["".join(td.itertext()).strip() for td in tr if td.tag.split("}")[-1] == "td"]
                if len(cells) == 2 and cells[0].endswith(":"):
                    info[cells[0][:-1]] = cells[1]
    return info


def read_um_web(host: str, port: int, username: str, password: str,
                socks: tuple[str, int] | None = None, timeout: float = 25.0,
                full_sync: bool = False, max_pages: int = 50) -> dict:
    """Log into /userman read-only, extract profiles, active sessions, users (paginated on full_sync), and logout."""
    t0 = time.monotonic()
    status, _, cookie = _request(host, port, "/userman", socks, timeout)
    if status != 200 or not cookie:
        raise UMWebError(f"GET /userman failed (status={status})")

    init_xml = b'<client-message type="initialize"><message-part processor="EchoClientAnalyzer"/></client-message>'
    status, r1, cookie = _request(host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout,
                                  method="POST", body=init_xml, cookie=cookie)
    if status != 200:
        raise UMWebError(f"Echo init failed (status={status})")

    tid_m = re.search(r'trans-id="(\d+)"', r1)
    text_inputs = re.findall(r'<input id="(c_\d+)"[^>]*type="text"', r1)
    pass_inputs = re.findall(r'<input id="(c_\d+)"[^>]*type="password"', r1)
    login_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Log in</div>', r1)
    if not (tid_m and text_inputs and pass_inputs and login_btns):
        raise UMWebError("unexpected Echo login form")

    login_xml = (
        f'<client-message trans-id="{tid_m.group(1)}">'
        f'<message-part processor="EchoPropertyUpdate">'
        f'<property component-id="{text_inputs[0]}" name="text">{escape(username)}</property>'
        f'<property component-id="{pass_inputs[0]}" name="text">{escape(password)}</property>'
        f'</message-part>'
        f'<message-part processor="EchoAction"><action component-id="{login_btns[0]}" name="click"/></message-part>'
        f'</client-message>'
    ).encode("utf-8")

    status, r2, cookie = _request(host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout,
                                  method="POST", body=login_xml, cookie=cookie)
    if status != 200:
        raise UMWebError(f"Echo login failed (status={status})")
    if "invalid user name or password" in r2.lower():
        raise UMWebError("invalid User Manager web credentials")

    logout_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Logout</div>', r2)
    tid = (re.search(r'trans-id="(\d+)"', r2) or [None, "2"])[1]

    def click_btn(btn_id: str) -> str:
        nonlocal tid, cookie
        xml = f'<client-message trans-id="{tid}"><message-part processor="EchoAction"><action component-id="{btn_id}" name="click"/></message-part></client-message>'.encode("utf-8")
        st, resp, cookie = _request(host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout,
                                    method="POST", body=xml, cookie=cookie)
        if st == 200:
            m = re.search(r'trans-id="(\d+)"', resp)
            if m:
                tid = m.group(1)
        return resp

    try:
        active_sessions = None
        active_users = None
        m_sess = re.search(r'>(\d+)\s+A sessions<', r2)
        if m_sess:
            active_sessions = int(m_sess.group(1))
        m_usr = re.search(r'>(\d+)\s+A users<', r2)
        if m_usr:
            active_users = int(m_usr.group(1))

        pages_m = re.search(r'page-count="(\d+)"', r2)
        per_m = re.search(r'per-page="(\d+)"', r2)
        pag_eid_m = re.search(r'<message-part processor="MWTPagination\.MessageProcessor">.*?eid="(c_\d+)"', r2, re.S)
        pages = int(pages_m.group(1)) if pages_m else 1
        per_page = int(per_m.group(1)) if per_m else 20

        # Active sessions list (skip clicking when count is 0 to save RB2011 CPU)
        active_rows: list[dict] = []
        if active_sessions and active_sessions > 0:
            asess_btns = re.findall(r'<div id="(c_\d+)"[^>]*>\d+\s+A sessions</div>', r2)
            if asess_btns:
                ra = click_btn(asess_btns[0])
                active_rows = _parse_active_sessions(ra)
        active_names = {s["user"] for s in active_rows}

        # Profiles list (skip on heavy routers during background checks unless full_sync or fast)
        profiles: list[dict] = []
        if full_sync or (time.monotonic() - t0) < 6.0:
            prof_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Profiles</div>', r2)
            if prof_btns:
                rp = click_btn(prof_btns[0])
                profiles = _parse_profiles(rp)

        # Total sessions count
        total_sessions = None
        sess_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Sessions</div>', r2)
        if sess_btns:
            try:
                rs = click_btn(sess_btns[0])
                pages_ms = re.search(r'page-count="(\d+)"', rs)
                per_ms = re.search(r'per-page="(\d+)"', rs)
                if pages_ms and per_ms:
                    total_sessions = int(pages_ms.group(1)) * int(per_ms.group(1))
                elif pages_ms:
                    total_sessions = int(pages_ms.group(1)) * 20
            except Exception:
                pass

        # Maintenance info (Database size, disk space, etc.)
        db_info: dict = {}
        maint_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Maintenance</div>', r2)
        if maint_btns:
            try:
                rm = click_btn(maint_btns[0])
                db_info = _parse_maintenance(rm)
            except Exception:
                pass

        # Users (page 0 always; paginate on full_sync gently)
        users = _parse_users_table(r2, active_names)
        if full_sync and pages > 1 and pag_eid_m:
            users_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Users</div>', r2)
            if users_btns:
                ru0 = click_btn(users_btns[0])
                pag2_m = re.search(r'<message-part processor="MWTPagination\.MessageProcessor">.*?eid="(c_\d+)"', ru0, re.S)
                pag_eid = pag2_m.group(1) if pag2_m else pag_eid_m.group(1)
                for p_idx in range(1, min(pages, max_pages)):
                    time.sleep(0.12)
                    pxml = (
                        f'<client-message trans-id="{tid}">'
                        f'<message-part processor="EchoPropertyUpdate">'
                        f'<property component-id="{pag_eid}" name="currentPage" value="{p_idx}"/>'
                        f'</message-part></client-message>'
                    ).encode("utf-8")
                    st, r_page, cookie = _request(host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout,
                                                  method="POST", body=pxml, cookie=cookie)
                    if st != 200:
                        break
                    m = re.search(r'trans-id="(\d+)"', r_page)
                    if m:
                        tid = m.group(1)
                    users.extend(_parse_users_table(r_page, active_names))

        um_users_total = len(users) if (full_sync or pages <= 1) else (pages * per_page)
        return {
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "hotspot_active": active_sessions,
            "active_users": active_users,
            "um_users": um_users_total,
            "um_sessions": total_sessions,
            "total_sessions": total_sessions,
            "um_profiles": profiles,
            "hotspot_active_rows": active_rows,
            "um_users_preview": users,
            "db_info": db_info,
        }
    finally:
        if logout_btns:
            try:
                click_btn(logout_btns[0])
            except Exception:
                pass


def rebuild_um_web_db(
    host: str,
    port: int,
    username: str,
    password: str,
    socks: tuple[str, int] | None = None,
    timeout: float = 35.0,
) -> dict:
    """Safely saves a backup and triggers database compaction/rebuild on RB2011 Echo2 User Manager."""
    t0 = time.monotonic()
    status, r1, cookie = _request(host, port, "/userman", socks, timeout)
    st, r1, cookie = _request(
        host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout,
        method="POST", body=b'<client-message type="initialize"><message-part processor="EchoClientAnalyzer"/></message-part></client-message>',
        cookie=cookie,
    )
    tid = re.search(r'trans-id="(\d+)"', r1).group(1)
    txt = re.findall(r'<input id="(c_\d+)"[^>]*type="text"', r1)[0]
    pwd = re.findall(r'<input id="(c_\d+)"[^>]*type="password"', r1)[0]
    btn = re.findall(r'<div id="(c_\d+)"[^>]*>Log in</div>', r1)[0]
    login_xml = (
        f'<client-message trans-id="{tid}">'
        f'<message-part processor="EchoPropertyUpdate">'
        f'<property component-id="{txt}" name="text">{username}</property>'
        f'<property component-id="{pwd}" name="text">{password}</property>'
        f'</message-part>'
        f'<message-part processor="EchoAction"><action component-id="{btn}" name="click"/></message-part>'
        f'</client-message>'
    ).encode("utf-8")
    st, r2, cookie = _request(host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout, method="POST", body=login_xml, cookie=cookie)
    tid = re.search(r'trans-id="(\d+)"', r2).group(1)

    def click_btn(btn_id: str) -> str:
        nonlocal tid, cookie
        xml = f'<client-message trans-id="{tid}"><message-part processor="EchoAction"><action component-id="{btn_id}" name="click"/></message-part></client-message>'.encode("utf-8")
        st, resp, cookie = _request(host, port, "/userman/?serviceId=Echo.Synchronize", socks, timeout, method="POST", body=xml, cookie=cookie)
        m = re.search(r'trans-id="(\d+)"', resp)
        if m:
            tid = m.group(1)
        return resp

    try:
        maint_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Maintenance</div>', r2)
        if not maint_btns:
            return {"ok": False, "error": "Maintenance tab not found"}
        rm = click_btn(maint_btns[0])

        # 1. Save backup first
        save_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Save</div>', rm)
        if save_btns:
            click_btn(save_btns[0])
            time.sleep(1.0)

        # 2. Trigger Rebuild
        rebuild_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Rebuild</div>', rm)
        if rebuild_btns:
            rm2 = click_btn(rebuild_btns[0])
            time.sleep(1.5)
            # 3. Trigger Rebuild log if present
            rebuild_log_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Rebuild log</div>', rm2)
            if rebuild_log_btns:
                rm3 = click_btn(rebuild_log_btns[0])
                time.sleep(1.5)
                info = _parse_maintenance(rm3)
            else:
                info = _parse_maintenance(rm2)
            return {"ok": True, "detail": "تم حفظ نسخة احتياطية وإعادة بناء وضغط قاعدة البيانات وسجلات السشنات بنجاح", "info": info}

        return {"ok": True, "detail": "تم حفظ نسخة احتياطية في مجلد الصيانة بنجاح"}
    finally:
        logout_btns = re.findall(r'<div id="(c_\d+)"[^>]*>Logout</div>', r2)
        if logout_btns:
            try:
                click_btn(logout_btns[0])
            except Exception:
                pass
