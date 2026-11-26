"""RouterOS API client (RouterOS v6.43+ and v7) with strict read/write separation.

Safety:
- `RouterOSApi.print()` ONLY permits commands in READ_ONLY_COMMANDS.
- `RouterOSApi.write_typed()` is blocked unless `allow_writes=True` AND the command
  is explicitly listed in TYPED_WRITE_ALLOWLIST with allowed parameter keys only.
"""
from __future__ import annotations

import hashlib
import socket

from .net import _recv_exact, open_tcp

READ_ONLY_COMMANDS = frozenset({
    "/system/identity/print",
    "/system/resource/print",
    "/system/routerboard/print",
    "/system/health/print",
    "/interface/print",
    "/interface/vlan/print",
    "/interface/bridge/print",
    "/ip/address/print",
    "/ip/pool/print",
    "/ip/dhcp-server/print",
    "/ip/hotspot/print",
    "/ip/hotspot/active/print",
    "/ip/hotspot/host/print",
    "/ip/hotspot/user/profile/print",
    "/tool/user-manager/user/print",
    "/tool/user-manager/session/print",
    "/tool/user-manager/profile/print",
    "/tool/user-manager/customer/print",
    "/user-manager/user/print",
    "/user-manager/user-profile/print",
    "/user-manager/session/print",
    "/user-manager/profile/print",
    "/user-manager/user/group/print",
    "/user-manager/limitation/print",
})

TYPED_WRITE_ALLOWLIST: dict[str, frozenset[str]] = {
    "/tool/user-manager/user/add": frozenset({"customer", "username", "password", "comment", "disabled"}),
    "/tool/user-manager/user/create-and-activate-profile": frozenset({"numbers", "profile", "customer"}),
    "/tool/user-manager/user/remove": frozenset({"numbers"}),
    "/tool/user-manager/session/remove": frozenset({"numbers"}),
    "/user-manager/user/add": frozenset({"name", "password", "group", "comment", "disabled"}),
    "/user-manager/user-profile/add": frozenset({"user", "profile"}),
    "/user-manager/user/remove": frozenset({"numbers"}),
    "/user-manager/session/remove": frozenset({"numbers"}),
}


class RouterOSError(Exception):
    pass


class NotAllowed(RouterOSError):
    pass


class WritesDisabled(RouterOSError):
    pass


def encode_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return (n | 0x8000).to_bytes(2, "big")
    if n < 0x200000:
        return (n | 0xC00000).to_bytes(3, "big")
    if n < 0x10000000:
        return (n | 0xE0000000).to_bytes(4, "big")
    return b"\xF0" + n.to_bytes(4, "big")


def decode_length(read) -> int:
    b = read(1)[0]
    if b < 0x80:
        return b
    if b < 0xC0:
        return ((b & 0x3F) << 8) | read(1)[0]
    if b < 0xE0:
        return ((b & 0x1F) << 16) | int.from_bytes(read(2), "big")
    if b < 0xF0:
        return ((b & 0x0F) << 24) | int.from_bytes(read(3), "big")
    return int.from_bytes(read(4), "big")


class RouterOSApi:
    def __init__(self, host: str, port: int, username: str, password: str,
                 socks: tuple[str, int] | None = None, timeout: float = 15.0,
                 allow_writes: bool = False):
        self.allow_writes = allow_writes
        self.sock: socket.socket = open_tcp(host, port, socks, timeout)
        self.sock.settimeout(timeout)
        try:
            self._login(username, password)
        except Exception:
            self.close()
            raise

    def _read(self, n: int) -> bytes:
        return _recv_exact(self.sock, n)

    def _send_sentence(self, words: list[str]) -> None:
        data = b"".join(encode_length(len(w.encode())) + w.encode() for w in words) + b"\x00"
        self.sock.sendall(data)

    def _read_sentence(self) -> list[str]:
        words = []
        while True:
            n = decode_length(self._read)
            if n == 0:
                return words
            words.append(self._read(n).decode("utf-8", "replace"))

    def _talk(self, words: list[str], max_rows: int | None = None) -> tuple[list[dict], dict]:
        self._send_sentence(words)
        rows, done = [], {}
        while True:
            sentence = self._read_sentence()
            if not sentence:
                continue
            kind, attrs = sentence[0], _attrs(sentence[1:])
            if kind == "!re":
                if max_rows is not None and len(rows) >= max_rows:
                    raise RouterOSError(f"row limit exceeded ({max_rows})")
                rows.append(attrs)
            elif kind == "!done":
                done = attrs
                return rows, done
            elif kind == "!trap":
                msg = attrs.get("message", "error")
                while True:
                    s = self._read_sentence()
                    if s and s[0] == "!done":
                        break
                raise RouterOSError(msg)
            elif kind == "!fatal":
                raise RouterOSError(" ".join(sentence[1:]) or "fatal")

    def _login(self, username: str, password: str) -> None:
        _, done = self._talk(["/login", f"=name={username}", f"=password={password}"])
        if "ret" in done:
            challenge = bytes.fromhex(done["ret"])
            digest = hashlib.md5(b"\x00" + password.encode() + challenge).hexdigest()
            self._talk(["/login", f"=name={username}", f"=response=00{digest}"])

    def print(self, command: str, count_only: bool = False,
              proplist: list[str] | None = None, max_rows: int | None = None,
              queries: list[str] | None = None) -> list[dict] | int:
        if command not in READ_ONLY_COMMANDS:
            raise NotAllowed(f"command not allowed: {command}")
        words = [command]
        if count_only:
            words.append("=count-only=")
        if proplist:
            words.append("=.proplist=" + ",".join(proplist))
        if queries:
            for q in queries:
                if not q.startswith("?"):
                    raise NotAllowed(f"invalid query word: {q}")
                words.append(q)
        rows, done = self._talk(words, max_rows=max_rows)
        if count_only:
            return int(done.get("ret", "0"))
        return rows

    def write_typed(self, command: str, params: dict[str, str]) -> str | None:
        """Execute a strictly allowlisted, typed write command when writes are explicitly enabled."""
        if command not in TYPED_WRITE_ALLOWLIST:
            raise NotAllowed(f"write command not allowed: {command}")
        if not self.allow_writes:
            raise WritesDisabled("router write operations are disabled (ALLOW_ROUTER_WRITES=false)")
        allowed_keys = TYPED_WRITE_ALLOWLIST[command]
        bad_keys = set(params.keys()) - allowed_keys
        if bad_keys:
            raise NotAllowed(f"disallowed parameter keys: {sorted(bad_keys)}")
        words = [command] + [f"={k}={v}" for k, v in params.items()]
        _, done = self._talk(words)
        return done.get("ret")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _attrs(words: list[str]) -> dict:
    out = {}
    for w in words:
        if w.startswith("="):
            k, _, v = w[1:].partition("=")
            out[k] = v
        elif w.startswith(".tag="):
            out[".tag"] = w[5:]
    return out
