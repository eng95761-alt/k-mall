from __future__ import annotations

import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken


def get_fernet(secret_key: str) -> Fernet:
    """Derive a 32-byte urlsafe-base64 key deterministically from the application SECRET_KEY."""
    derived = hashlib.sha256(secret_key.encode("utf-8")).digest()
    b64_key = base64.urlsafe_b64encode(derived)
    return Fernet(b64_key)


def encrypt_text(plain: str, secret_key: str) -> str:
    if not plain:
        return ""
    f = get_fernet(secret_key)
    return f.encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_text(cipher: str, secret_key: str) -> str:
    if not cipher:
        return ""
    f = get_fernet(secret_key)
    try:
        return f.decrypt(cipher.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        # Fallback to plain if not encrypted (for backward-compatibility with plain legacy data)
        return cipher
