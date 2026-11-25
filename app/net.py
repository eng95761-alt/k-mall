"""Network helpers: open TCP connections, optionally through the local SOCKS5
proxy that wireproxy provides (the Back to Home tunnel into the mall)."""
from __future__ import annotations

import socket
import struct
import time

SOCKS_REPLY = {
    0: "ok", 1: "general failure", 2: "not allowed", 3: "network unreachable",
    4: "host unreachable", 5: "connection refused", 6: "ttl expired",
}


class NetError(Exception):
    pass


def open_tcp(host: str, port: int, socks: tuple[str, int] | None, timeout: float = 10.0) -> socket.socket:
    """Return a connected socket to host:port. Uses SOCKS5 (no auth) when `socks` is set."""
    if socks is None:
        return socket.create_connection((host, port), timeout=timeout)

    s = socket.create_connection(socks, timeout=timeout)
    try:
        s.sendall(b"\x05\x01\x00")
        if _recv_exact(s, 2) != b"\x05\x00":
            raise NetError("SOCKS proxy refused handshake")
        try:
            addr = b"\x01" + socket.inet_aton(host)
        except OSError:
            name = host.encode()
            addr = b"\x03" + bytes([len(name)]) + name
        s.sendall(b"\x05\x01\x00" + addr + struct.pack(">H", port))
        head = _recv_exact(s, 4)
        if head[1] != 0:
            raise NetError(f"tunnel: {SOCKS_REPLY.get(head[1], head[1])}")
        atyp = head[3]
        if atyp == 1:
            _recv_exact(s, 4 + 2)
        elif atyp == 3:
            _recv_exact(s, _recv_exact(s, 1)[0] + 2)
        elif atyp == 4:
            _recv_exact(s, 16 + 2)
        return s
    except Exception:
        s.close()
        raise


def tcp_probe(host: str, port: int, socks: tuple[str, int] | None, timeout: float = 10.0) -> float:
    """Connect and close. Returns latency in ms; raises on failure."""
    t0 = time.monotonic()
    s = open_tcp(host, port, socks, timeout)
    s.close()
    return (time.monotonic() - t0) * 1000.0


def _recv_exact(s: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise NetError("connection closed")
        buf += chunk
    return buf
