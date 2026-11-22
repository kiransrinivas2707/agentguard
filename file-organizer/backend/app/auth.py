from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

import jwt

from .config import Settings

COOKIE_NAME = "fo_session"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
_MAX_FAILURES = 10
_WINDOW_SECONDS = 15 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(digest_hex)),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_token(user_id: str, settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.token_ttl_hours * 3600,
    }
    return jwt.encode(payload, settings.secret, algorithm="HS256")


def decode_token(token: str, settings: Settings) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret, algorithms=["HS256"])
        subject = payload.get("sub")
        return subject if isinstance(subject, str) else None
    except jwt.PyJWTError:
        return None


def set_session_cookie(response, token: str, settings: Settings) -> None:  # type: ignore[no-untyped-def]
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.token_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session_cookie(response) -> None:  # type: ignore[no-untyped-def]
    response.delete_cookie(COOKIE_NAME, path="/")


class LoginThrottle:
    """Small in-memory failed-login throttle (per process)."""

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        entries = self._failures[key]
        while entries and now - entries[0] > _WINDOW_SECONDS:
            entries.popleft()
        return entries

    def is_blocked(self, key: str) -> bool:
        return len(self._prune(key, time.time())) >= _MAX_FAILURES

    def record_failure(self, key: str) -> None:
        self._prune(key, time.time()).append(time.time())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)
