"""Security utilities for password hashing, tokens, rate limiting, and session cookies."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

SESSION_COOKIE_NAME = "serene_session"
SESSION_TTL_DAYS = 30
AUTH_CODE_TTL_MINUTES = 15
MAX_CODE_ATTEMPTS = 5


class RateLimiter:
    """Thread-safe in-memory sliding-window rate limiter for auth endpoints."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        """Raise HTTP 429 if `key` exceeded `limit` calls inside `window_seconds`."""
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="Too many attempts. Please pause for a few minutes and try again.",
                )
            bucket.append(now)

    def reset(self) -> None:
        """Clear tracked hits (useful in test isolation)."""
        with self._lock:
            self._hits.clear()


auth_rate_limiter = RateLimiter()


def utc_now() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return utc_now().isoformat()


def hash_secret(secret: str) -> str:
    """Hash a password or PIN using salted scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_secret(secret: str, stored_hash: str | None) -> bool:
    """Verify a plaintext password or PIN against a stored scrypt hash."""
    if not stored_hash or not stored_hash.startswith("scrypt$"):
        return False
    try:
        _, salt_hex, hash_hex = stored_hash.split("$", 2)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    derived = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return hmac.compare_digest(derived, expected)


def hash_token(raw_token: str) -> str:
    """Hash a session token or OTP code with SHA-256."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def generate_session_token() -> tuple[str, str, str]:
    """Return (raw_token, token_hash, expires_at_iso)."""
    raw = secrets.token_urlsafe(32)
    expires = (utc_now() + timedelta(days=SESSION_TTL_DAYS)).isoformat()
    return raw, hash_token(raw), expires


def generate_numeric_otp(digits: int = 6) -> str:
    """Generate a cryptographically random numeric OTP."""
    upper = 10**digits
    return f"{secrets.randbelow(upper):0{digits}d}"
