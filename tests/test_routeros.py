import socket
import threading

import pytest

from app.routeros import (NotAllowed, RouterOSApi, RouterOSError, decode_length,
                          encode_length)


@pytest.mark.parametrize("n", [0, 1, 0x7F, 0x80, 0x3FFF, 0x4000, 0x1FFFFF, 0x200000, 0xFFFFFFF, 0x10000000])
def test_length_roundtrip(n):
    data = encode_length(n)
    pos = [0]

    def read(k):
        out = data[pos[0]:pos[0] + k]
        pos[0] += k
        return out

    assert decode_length(read) == n
    assert pos[0] == len(data)


class FakeRouter:
    """Speaks just enough RouterOS API to test the client. Records every command received."""

    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.received = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.srv.accept()
        f = conn.makefile("rb")

        def read(k):
            return f.read(k)

        def send(*words):
            conn.sendall(b"".join(encode_length(len(w.encode())) + w.encode() for w in words) + b"\x00")

        while True:
            words = []
            try:
                while (n := decode_length(read)) != 0:
                    words.append(read(n).decode())
            except (IndexError, OSError):
                return
            cmd = words[0]
            self.received.append(words)
            if cmd == "/login":
                if "=password=good" in words:
                    send("!done")
                else:
                    send("!trap", "=message=invalid user name or password (6)")
                    send("!done")
            elif cmd == "/system/resource/print":
                send("!re", "=cpu-load=7", "=free-memory=1000", "=total-memory=4000", "=version=6.49.21")
                send("!done")
            elif "=count-only=" in words:
                send("!done", "=ret=42")
            else:
                send("!trap", "=message=no such command")
                send("!done")


def test_login_print_and_count():
    fake = FakeRouter()
    with RouterOSApi("127.0.0.1", fake.port, "admin", "good") as api:
        rows = api.print("/system/resource/print")
        assert rows == [{"cpu-load": "7", "free-memory": "1000", "total-memory": "4000", "version": "6.49.21"}]
        assert api.print("/ip/hotspot/active/print", count_only=True) == 42


def test_bad_password_raises():
    fake = FakeRouter()
    with pytest.raises(RouterOSError):
        RouterOSApi("127.0.0.1", fake.port, "admin", "bad")


@pytest.mark.parametrize("cmd", ["/system/reboot", "/user/add", "/ip/hotspot/user/remove",
                                 "/tool/user-manager/user/add", "/user-manager/user/remove", "/export",
                                 "/system/script/run", "/interface/set"])
def test_write_commands_never_sent(cmd):
    fake = FakeRouter()
    with RouterOSApi("127.0.0.1", fake.port, "admin", "good") as api:
        with pytest.raises(NotAllowed):
            api.print(cmd)
        api.print("/system/resource/print")  # connection still usable
    assert all(words[0] != cmd for words in fake.received)
