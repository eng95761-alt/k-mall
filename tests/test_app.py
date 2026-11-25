from fastapi.testclient import TestClient

from app import main
from app.collector import store
from app.config import RouterDef
from app.db import Alert
from app.security import hash_password, verify_password

H = {"X-Kmall": "1"}


def client():
    return TestClient(main.app)


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
        r = c.post("/api/login", json={"username": "owner", "password": "test-password-123"}, headers=H)
        assert r.status_code == 200, r.text
        r = c.get("/api/overview")
        assert r.status_code == 200
        assert r.json()["totals"]["routers"] == 0
        assert r.json()["now"].endswith(("Z", "+00:00"))
        assert r.headers["Cache-Control"] == "no-store"
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
        c.post("/api/logout", headers=H)
        assert c.get("/api/overview").status_code == 401


def test_rate_limit():
    main.limiter.fails.clear()
    with client() as c:
        for _ in range(5):
            assert c.post("/api/login", json={"username": "owner", "password": "nope"}, headers=H).status_code == 401
        assert c.post("/api/login", json={"username": "owner", "password": "test-password-123"},
                      headers=H).status_code == 429
    main.limiter.fails.clear()


def test_store_and_alerts():
    r = RouterDef(id="t1", name="Test", host="127.0.0.1", method="api", port=8728)
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


def test_utc_marks_naive_times():
    from datetime import datetime
    assert main.utc(datetime(2026, 1, 1, 12, 0)).isoformat().endswith("+00:00")
    assert main.utc(None) is None
