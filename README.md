# K-Mall Network Platform

Arabic RTL web platform for monitoring the commercial complex's MikroTik routers, generating/printing voucher batches, and managing local commercial subscriptions.

## Lightweight Free-Tier Design (GitHub + Render Free)
- **Zero frontend build tools** (no Node/React/npm bloat): total static UI is `< 60 KB`.
- **Tiny backend** (`5` Python packages + `wireproxy`): runs well within Render Free Tier's `512 MB` RAM limit.
- **Database footprint control:** `HISTORY_DAYS=14` default keeps PostgreSQL storage minimal.
- **Note on Render Free Tier:** Free web services sleep after 15 minutes of inactivity unless pinged on `/healthz` by a free uptime monitor, and Render's free PostgreSQL tier has a 30-day lifespan (or supply any external free PostgreSQL `DATABASE_URL`).

## Features
- **Dashboard & SVG Charts:** Live CPU/RAM/Storage progress meters, latency, active Hotspot users, User Manager users/sessions, interface traffic, and VLANs.
- **Vouchers & Controlled Card Creation:** Generate secure random voucher batches, print A4 card sheets, export CSV, and push to User Manager (`v6` & `v7`) only via typed allowlist (`ALLOW_ROUTER_WRITES=true`) + explicit owner approval + permanent `ChangeLog`.
- **Dual Collection Adapters:** RouterOS API (`8728`) with `alt_hosts` fallback + safe low-frequency Echo2 User Manager Web (`:800`) reader over SOCKS5.
- **Topology, Commercial Ledger, RBAC & Audit:** VLAN map, Plans/Customers/Subscriptions/IQD Payments, configurable alert thresholds, `owner`/`staff`/`viewer` roles, and CSV reports.

## Local Development & Tests
```
.venv\Scripts\python -m pytest -v
.venv\Scripts\python run_local.py
```
