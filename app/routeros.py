"""Minimal, READ-ONLY RouterOS API client (RouterOS v6.43+ and v7).

Safety: only commands listed in READ_ONLY_COMMANDS can be sent. Every other
command (add/set/remove/reboot/...) raises before anything reaches the router.
"""
from __future__ import annotations

import hashlib
import socket

from .net import _recv_exact, open_tcp

READ_ONLY_COMMANDS = frozenset({
    "/system/identity/print",
    "/system/resource/print",
    "/system/routerboard/print",
    "/interface/print",
    "/ip/hotspot/active/print",
    "/ip/hotspot/host/print",
    "/tool/user-manager/user/print",      # User Manager v6 (legacy package)
    "/tool/user-manager/session/print",
    "/user-manager/user/print",           # User Manager v7 (integrated)
    "/user-manager/session/print",
})


class RouterOSError(Exception):
    pass


class NotAllowed(RouterOSError):
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
                 socks: tuple[str, int] | None = None, timeout: float = 15.0):
        self.sock: socket.socket = open_tcp(host, port, socks, timeout)
        self.sock.settimeout(timeout)
        try:
            self._login(username, password)
        except Exception:
            self.close()
            raise

    # ---- wire protocol ----
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

    def _talk(self, words: list[str]) -> tuple[list[dict], dict]:
        self._send_sentence(words)
        rows, done = [], {}
        while True:
            sentence = self._read_sentence()
            if not sentence:
                continue
            kind, attrs = sentence[0], _attrs(sentence[1:])
            if kind == "!re":
                rows.append(attrs)
            elif kind == "!done":
                done = attrs
                return rows, done
            elif kind == "!trap":
                # drain until !done, then raise
                msg = attrs.get("message", "error")
                while (s := self._read_sentence()) and s[0] != "!done":
                    pass
                raise RouterOSError(msg)
            elif kind == "!fatal":
                raise RouterOSError(" ".join(sentence[1:]) or "fatal")

    def _login(self, username: str, password: str) -> None:
        _, done = self._talk(["/login", f"=name={username}", f"=password={password}"])
        if "ret" in done:  # pre-6.43 challenge/response
            challenge = bytes.fromhex(done["ret"])
            digest = hashlib.md5(b"\x00" + password.encode() + challenge).hexdigest()
            self._talk(["/login", f"=name={username}", f"=response=00{digest}"])

    # ---- public, read-only ----
    def print(self, command: str, count_only: bool = False, proplist: list[str] | None = None) -> list[dict] | int:
        if command not in READ_ONLY_COMMANDS:
            raise NotAllowed(f"command not allowed: {command}")
        words = [command]
        if count_only:
            words.append("=count-only=")
        if proplist:
            words.append("=.proplist=" + ",".join(proplist))
        rows, done = self._talk(words)
        if count_only:
            return int(done.get("ret", "0"))
        return rows

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
