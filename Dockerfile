# Stage 1: Build React/Tailwind frontend at Docker build time
FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python runtime (zero Node.js overhead)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# wireproxy (userspace WireGuard → local SOCKS5). Pinned version, checksum verified.
ARG WIREPROXY_VERSION=v1.1.3
ARG WIREPROXY_SHA256=e88c1d090740373fc606c1bafd81d9a5eadc642cce5667616e20e9d7a444f51c
RUN python - <<'EOF'
import hashlib, io, os, tarfile, urllib.request
v, want = os.environ["WIREPROXY_VERSION"], os.environ["WIREPROXY_SHA256"]
url = f"https://github.com/windtf/wireproxy/releases/download/{v}/wireproxy_linux_amd64.tar.gz"
data = urllib.request.urlopen(url, timeout=60).read()
got = hashlib.sha256(data).hexdigest()
assert got == want, f"wireproxy checksum mismatch: {got}"
with tarfile.open(fileobj=io.BytesIO(data)) as t:
    m = t.getmember("wireproxy")
    with open("/usr/local/bin/wireproxy", "wb") as f:
        f.write(t.extractfile(m).read())
os.chmod("/usr/local/bin/wireproxy", 0o755)
print("wireproxy", v, "installed, sha256 ok")
EOF

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY --from=frontend-builder /build/app/static ./app/static
COPY start.sh .
RUN chmod +x start.sh && useradd --create-home --uid 10001 kmall
USER kmall

EXPOSE 10000
CMD ["./start.sh"]
