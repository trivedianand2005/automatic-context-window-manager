"""Password hashing and opaque session-token helpers (standard library only).

The service currently issues opaque random session tokens stored server-side.
There is no JWT support yet.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, salt: str | None = None) -> str:
    """Return ``salt$hexdigest`` using PBKDF2-HMAC-SHA256."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, _, expected = stored.partition("$")
    candidate = hash_password(password, salt).partition("$")[2]
    return hmac.compare_digest(candidate, expected)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)
