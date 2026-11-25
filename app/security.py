from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


class LoginLimiter:
    """At most `limit` failed logins per IP per `window` seconds."""

    def __init__(self, limit: int = 5, window: int = 900):
        self.limit, self.window = limit, window
        self.fails: dict[str, deque] = defaultdict(deque)

    def blocked(self, ip: str) -> bool:
        q, now = self.fails[ip], time.monotonic()
        while q and now - q[0] > self.window:
            q.popleft()
        return len(q) >= self.limit

    def fail(self, ip: str) -> None:
        self.fails[ip].append(time.monotonic())

    def reset(self, ip: str) -> None:
        self.fails.pop(ip, None)


SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
