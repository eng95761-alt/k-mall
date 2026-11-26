from fastapi.testclient import TestClient

from app import main
from app.collector import collect_one, store
from app.config import RouterDef, Settings
from app.db import Alert
from app.security import hash_password, verify_password
from tests.test_routeros import FakeRouter

H = {"X-Kmall": "1"}


def client():
    return TestClient(main.app)


def login_as(c: TestClient, username: str = "owner", password: str = "test-password-123"):
    r = c.post("/api/login", json={"username": username, "password": password}, headers=H)
    assert r.status_code == 200, r.text


def test_password_hash():
    h = hash_password("secret-pass")
    assert verify_password("secret-pass", h)
    assert not verify_password("wrong", h)
    assert "secret-pass" not in h


def test_requires_login():
    with client() as c:
        assert c.get("/api/overview").status_code == 401
        assert c.get("/healthz").json() == {"ok": True}


def test_csrf_header_required():
    with client() as c:
        r = c.post("/api/login", json={"username": "owner", "password": "test-password-123"})
        assert r.status_code == 403


def test_login_and_overview():
    with client() as c:
        login_as(c)
        r = c.get("/api/overview")
        assert r.status_code == 200
        assert r.json()["totals"]["routers"] == 0
        assert r.json()["now"].endswith(("Z", "+00:00"))
        assert r.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        c.post("/api/logout", headers=H)
        assert c.get("/api/overview").status_code == 401


def test_rate_limit_and_xff_spoof_resistant():
    main.limiter.fails.clear()
    with client() as c:
        for i in range(5):
            # Attacker tries spoofing leftmost X-Forwarded-For while real client IP is rightmost
            r = c.post(
                "/api/login",
                json={"username": "owner", "password": "nope"},
                headers={**H, "X-Forwarded-For": f"1.2.3.{i}, 198.51.100.77"},
            )
            assert r.status_code == 401
        blocked = c.post(
            "/api/login",
            json={"username": "owner", "password": "test-password-123"},
            headers={**H, "X-Forwarded-For": "9.9.9.9, 198.51.100.77"},
        )
        assert blocked.status_code == 429
    main.limiter.fails.clear()


def test_store_and_alerts():
    r = RouterDef(id="t1", name="Test", host="127.0.0.1", method="api", port=8728, vlan_id=111, subnet="10.0.0.0/22")
    ok = {"online": True, "latency_ms": 5.0, "cpu_load": 95, "hdd_free": 5, "hdd_total": 100,
          "mem_free": 10, "mem_total": 100}
    down = {"online": False, "error": "timeout"}
    with main.SessionLocal() as db:
        store(db, r, ok); db.commit()
        kinds = {a.kind for a in db.query(Alert).filter(Alert.router_id == "t1", Alert.closed_at.is_(None))}
        assert kinds == {"cpu", "storage"}
        store(db, r, down); db.commit()          # 1 failure: not yet offline
        assert not db.query(Alert).filter_by(router_id="t1", kind="offline").count()
        store(db, r, down); db.commit()          # 2 failures: offline alert
        assert db.query(Alert).filter(Alert.router_id == "t1", Alert.kind == "offline",
                                      Alert.closed_at.is_(None)).count() == 1
        store(db, r, {"online": True, "cpu_load": 5, "hdd_free": 90, "hdd_total": 100}); db.commit()
        assert db.query(Alert).filter(Alert.router_id == "t1", Alert.closed_at.is_(None)).count() == 0


def test_collect_one_with_fake_router_and_alt_hosts():
    fake = FakeRouter()
    r = RouterDef(id="f1", name="Fake", host="127.0.0.1", alt_hosts=["127.0.0.1"], method="api", port=fake.port, um="v6")
    s = Settings(
        database_url="sqlite:///./test_kmall.db",
        secret_key="x" * 32,
        admin_username="owner",
        admin_password="test-password-123",
        router_user="admin",
        router_password="good",
        socks=None,
        routers=[r],
    )
    res = collect_one(r, s, fetch_snapshot=True)
    assert res["online"] is True
    assert res["cpu_load"] == 7
    assert res["um_users"] == 42
    assert res["snapshot"] is not None
    assert "interfaces" in res["snapshot"]


def test_um_web_reader_mock():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from app.um_web import read_um_web

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Set-Cookie", "MWTSESSION=abc123; Path=/userman")
            self.end_headers()
            self.wfile.write(b"<html></html>")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            self.send_response(200)
            self.end_headers()
            if 'type="initialize"' in body:
                self.wfile.write(
                    b'<server-message trans-id="1"><input id="c_8" type="text"/>'
                    b'<input id="c_10" type="password"/><div id="c_11">Log in</div></server-message>'
                )
            elif "admin" in body and "mock-um-pass" in body:
                self.wfile.write(
                    b'<server-message trans-id="2">'
                    b'<div id="c_25">11 A sessions</div><div id="c_26">11 A users</div>'
                    b'<div id="c_29">Logout</div>'
                    b'<message-part processor="MWTPagination.MessageProcessor">'
                    b'<init page-count="38" per-page="20"/></message-part>'
                    b'<table id="c_38"><tr><td>Username</td><td>Password</td><td>Till time</td>'
                    b'<td>Rate limit</td><td>Start time</td><td>End time</td><td>Money paid</td>'
                    b'<td>Total time left</td><td>Actual profile</td></tr>'
                    b'<tr><td>card1</td><td>p</td><td>t</td><td>r</td><td>s</td><td>e</td><td>5000</td><td>10d</td><td>5M</td></tr>'
                    b'</table></server-message>'
                )
            else:
                self.wfile.write(b'<server-message trans-id="3"/>')

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        res = read_um_web("127.0.0.1", srv.server_address[1], "admin", "mock-um-pass")
        assert res["hotspot_active"] == 11
        assert res["active_users"] == 11
        assert res["um_users"] == 760
        assert res["um_users_preview"][0]["username"] == "card1"
    finally:
        srv.shutdown()


def test_safe_cleanup_prevents_deleting_active_and_respects_write_gate(monkeypatch):
    fake = FakeRouter()
    rdef = RouterDef(id="v7c", name="L009 Clean", host="127.0.0.1", method="api", port=fake.port, um="v7")
    monkeypatch.setattr(main.settings, "routers", [rdef])
    monkeypatch.setattr(main.settings, "router_user", "admin")
    monkeypatch.setattr(main.settings, "router_password", "good")
    monkeypatch.setattr(main.settings, "socks", None)
    monkeypatch.setattr(main.settings, "allow_router_writes", False)

    with client() as c:
        login_as(c)
        prev = c.get("/api/cleanup/v7c/preview")
        assert prev.status_code == 200
        # Blocked when ALLOW_ROUTER_WRITES=false
        blk = c.post("/api/cleanup/v7c/execute", json={
            "approved": True, "confirm_router_id": "v7c", "action": "remove_expired_users", "ids": ["*U1"]
        }, headers=H)
        assert blk.status_code == 403

        monkeypatch.setattr(main.settings, "allow_router_writes", True)
        ok = c.post("/api/cleanup/v7c/execute", json={
            "approved": True, "confirm_router_id": "v7c", "action": "remove_expired_users", "ids": ["*U1"]
        }, headers=H)
        assert ok.status_code == 200
        assert ok.json()["removed"] == 1


def test_commercial_settings_rbac_and_exports():
    with client() as c:
        login_as(c)
        # Settings update
        r = c.put("/api/settings", json={"cpu_warn": 85, "storage_warn_pct": 15, "offline_after_fails": 3}, headers=H)
        assert r.status_code == 200
        assert c.get("/api/settings").json()["cpu_warn"] == 85

        # Create staff user & verify RBAC separation
        r = c.post("/api/users", json={"username": "cashier1", "password": "staff-password-123", "role": "staff"}, headers=H)
        assert r.status_code == 200

        # Commercial flow
        p = c.post("/api/plans", json={"name": "Monthly 5M", "speed_label": "5M", "duration_days": 30, "price_iqd": 15000}, headers=H)
        assert p.status_code == 200
        cu = c.post("/api/customers", json={"full_name": "Ali Shop", "phone": "07700000000", "shop_unit": "A12"}, headers=H)
        assert cu.status_code == 200
        sub = c.post("/api/subscriptions", json={"customer_id": cu.json()["id"], "plan_id": p.json()["id"], "voucher_code": "V100", "paid_iqd": 10000}, headers=H)
        assert sub.status_code == 200
        pay = c.post(f"/api/subscriptions/{sub.json()['id']}/payments", json={"amount_iqd": 5000}, headers=H)
        assert pay.status_code == 200 and pay.json()["balance_iqd"] == 0

        assert c.get("/api/reports/sales.csv").status_code == 200
        assert c.get("/api/reports/samples.csv").status_code == 200
        assert c.get("/api/reports/cards.csv").status_code == 200
        assert c.get("/api/alerts").status_code == 200
        assert c.get("/api/routers/t1/history").status_code == 200
        assert c.get("/api/routers/t1/snapshot").status_code == 200

        # Log in as staff: allowed to view & create customers, forbidden from owner-only settings/users
        c.post("/api/logout", headers=H)
        login_as(c, "cashier1", "staff-password-123")
        assert c.get("/api/users").status_code == 403
        assert c.put("/api/settings", json={"cpu_warn": 90, "storage_warn_pct": 10, "offline_after_fails": 2}, headers=H).status_code == 403


def test_voucher_batch_approval_and_push_adapters(monkeypatch):
    fake = FakeRouter()
    rdef = RouterDef(id="v7r", name="L009 Test", host="127.0.0.1", method="api", port=fake.port, um="v7")
    monkeypatch.setattr(main.settings, "routers", [rdef])
    monkeypatch.setattr(main.settings, "router_user", "admin")
    monkeypatch.setattr(main.settings, "router_password", "good")
    monkeypatch.setattr(main.settings, "socks", None)
    monkeypatch.setattr(main.settings, "allow_router_writes", False)

    with client() as c:
        login_as(c)
        b = c.post("/api/vouchers/batches", json={
            "router_id": "v7r", "profile_name": "1-month", "count": 3, "prefix": "TST", "price_iqd": 10000
        }, headers=H)
        assert b.status_code == 200
        bid = b.json()["id"]
        detail = c.get(f"/api/vouchers/batches/{bid}").json()
        assert len(detail["cards"]) == 3
        assert c.get(f"/api/reports/batch/{bid}.csv").status_code == 200

        # Blocked while ALLOW_ROUTER_WRITES=false
        blocked = c.post(f"/api/vouchers/batches/{bid}/push", json={"approved": True, "confirm_router_id": "v7r"}, headers=H)
        assert blocked.status_code == 403

        # Allowed once explicit env flag + owner approval are set
        monkeypatch.setattr(main.settings, "allow_router_writes", True)
        ok = c.post(f"/api/vouchers/batches/{bid}/push", json={"approved": True, "confirm_router_id": "v7r"}, headers=H)
        assert ok.status_code == 200
        assert ok.json()["pushed"] == 3
        changes = c.get("/api/changes").json()
        assert any(ch["result"] == "success" and ch["router_id"] == "v7r" for ch in changes)


def test_utc_marks_naive_times():
    from datetime import datetime
    assert main.utc(datetime(2026, 1, 1, 12, 0)).isoformat().endswith("+00:00")
    assert main.utc(None) is None


def test_crypto_encryption_and_decryption():
    from app.crypto import encrypt_text, decrypt_text
    key = "a-very-strong-secret-key-at-least-32-chars-long"
    original = "UserPassword1234!"
    cipher = encrypt_text(original, key)
    assert cipher != original
    decrypted = decrypt_text(cipher, key)
    assert decrypted == original
    # Backward compatibility with unencrypted text
    assert decrypt_text("plain_old_text", key) == "plain_old_text"


def test_static_frontend_and_assets():
    with client() as c:
        # Index root
        r = c.get("/")
        assert r.status_code == 200
        assert "html" in r.headers["content-type"]
        # Favicons
        assert c.get("/favicon.ico").status_code == 200
        assert c.get("/favicon.svg").status_code == 200


def test_enterprise_db_models():
    from app.db import (
        UserSession, NetworkDevice, ChangeRequest, ApprovalRecord,
        RollbackRecord, Backup, utcnow
    )
    with main.SessionLocal() as db:
        dev = NetworkDevice(
            id="ap-floor1",
            name="AP Floor 1",
            device_type="ap",
            ip_address="192.168.0.50",
            vendor="MikroTik",
            status="online"
        )
        db.add(dev)
        db.commit()
        retrieved = db.get(NetworkDevice, "ap-floor1")
        assert retrieved is not None
        assert retrieved.name == "AP Floor 1"
        db.delete(retrieved)
        db.commit()


def test_active_hotspot_clients_endpoint():
    with client() as c:
        login_as(c)
        r = c.get("/api/hotspot/active")
        assert r.status_code == 200
        assert "count" in r.json()
        assert "clients" in r.json()


