"""Local development runner: loads .env, optionally starts wireproxy, then the app.

    python run_local.py

Optional .env keys for the tunnel:
    WIREPROXY_EXE=path/to/wireproxy(.exe)
    BTH_WG_CONFIG_FILE=path/to/bth.conf
"""
import atexit
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def start_tunnel() -> None:
    exe, conf = os.environ.get("WIREPROXY_EXE"), os.environ.get("BTH_WG_CONFIG_FILE")
    if not (exe and conf):
        print("tunnel: WIREPROXY_EXE / BTH_WG_CONFIG_FILE not set — skipping")
        return
    socks = os.environ.get("SOCKS_PROXY", "127.0.0.1:25344")
    cfg = Path(tempfile.mkdtemp()) / "wireproxy.conf"
    cfg.write_text(f"WGConfig = {conf}\n\n[Socks5]\nBindAddress = {socks}\n", encoding="utf-8")
    proc = subprocess.Popen([exe, "-s", "-c", str(cfg)])
    atexit.register(proc.terminate)
    print(f"tunnel: wireproxy started (pid {proc.pid}) on {socks}")
    import socket, time
    host, _, port_s = socks.rpartition(":")
    for _ in range(20):
        s = socket.socket()
        s.settimeout(0.2)
        if s.connect_ex((host, int(port_s))) == 0:
            s.close()
            break
        s.close()
        time.sleep(0.2)
    time.sleep(2.0)


if __name__ == "__main__":
    load_env(ROOT / ".env")
    start_tunnel()
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
