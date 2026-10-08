
"""Symmetric encryption helpers (Fernet).

Used to encrypt sensitive config values (API keys) at rest in the DB.
The master key is derived from APP_SECRET_KEY so the DB on its own is
useless without the running server's secret.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..core.config import settings


_fernet_singleton: Fernet | None = None


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte urlsafe-base64 key from any-length secret."""
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    global _fernet_singleton
    if _fernet_singleton is None:
        _fernet_singleton = Fernet(_derive_key(settings.APP_SECRET_KEY or "change-me"))
    return _fernet_singleton


def encrypt(value: str) -> str:
    if value is None or value == "":
        return ""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""


def mask(value: str, keep: int = 4) -> str:
    """Return a masked representation for display, e.g. ****1234."""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]
