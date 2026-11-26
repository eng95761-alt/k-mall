#!/bin/sh
set -eu

# Open the Back to Home tunnel if its config is provided (Render secret env var).
if [ -n "${BTH_WG_CONFIG_B64:-}" ]; then
  umask 077
  mkdir -p /tmp/kmall
  printf '%s' "$BTH_WG_CONFIG_B64" | tr -d '\r\n \t' | base64 -d > /tmp/kmall/bth.conf
  printf 'WGConfig = /tmp/kmall/bth.conf\n\n[Socks5]\nBindAddress = 127.0.0.1:25344\n' > /tmp/kmall/wireproxy.conf
  # keep the tunnel alive: restart it if it ever exits
  ( while true; do wireproxy -s -c /tmp/kmall/wireproxy.conf || true; echo "wireproxy exited, restarting in 5s"; sleep 5; done ) &
else
  echo "BTH_WG_CONFIG_B64 not set — tunnel disabled"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers --forwarded-allow-ips="*"
