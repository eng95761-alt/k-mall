# K-Mall Network Platform

Arabic web dashboard that monitors the complex's MikroTik routers from anywhere.
**Read-only**: it never changes router configuration.

```
browser (any network) ─HTTPS→ Render: FastAPI app + collector + wireproxy
                                         │ WireGuard (MikroTik Back to Home)
                                         ▼
                                   main router LAN → complex routers
```

## What it shows (phase 1)
- Each router: online/offline, response time, last check, last success.
- Routers with RouterOS API access: CPU, RAM, storage, RouterOS version, uptime,
  connected hotspot customers, User Manager card and session counts.
- Routers without API access: reachability only.
- Alerts: offline (2 missed checks), CPU ≥ 90 %, storage < 10 % free. Open and close automatically.
- 30 days of history (pruned automatically).

## Safety
- `app/routeros.py` sends only commands in `READ_ONLY_COMMANDS`; anything else raises before reaching the router (tested).
- No free-form command endpoint exists.
- All secrets come from environment variables; none are in this repository.
- Login: PBKDF2-SHA256 (600k iterations), 12 h sessions (HttpOnly, SameSite=Strict, Secure on Render),
  5 failed logins / 15 min per IP, CSRF header check, strict Content-Security-Policy.

## Configuration (environment variables)
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL (Render sets it); SQLite locally |
| `SECRET_KEY` | session signing key, ≥ 32 chars (Render generates it) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | owner account created on first start (password ≥ 10 chars) |
| `ROUTER_API_USER`, `ROUTER_API_PASSWORD` | RouterOS API login used for reading |
| `ROUTERS_JSON` | router inventory (see `.env.example`) |
| `BTH_WG_CONFIG_B64` | base64 of the Back to Home WireGuard client config |
| `COLLECT_INTERVAL` | seconds between checks (default 60) |

## Deploy on Render
1. New → **Blueprint** → select this repository → Render reads `render.yaml` (web service + PostgreSQL).
2. Fill the variables marked "sync: false" in the dashboard.
3. Deploy. Open the service URL and log in with `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

## Local development
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest httpx
copy .env.example .env      # edit values
.venv\Scripts\python run_local.py
.venv\Scripts\python -m pytest
```
