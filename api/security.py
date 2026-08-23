"""JWT session-cookie minting/verification and CSRF token generation.

Security-critical: this is the module `api/deps.py::get_current_user` and
`api/routers/auth.py` rely on to decide who is signed in. Keep changes here conservative and
covered by `tests/test_api_auth.py`.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

import jwt

from core.auth_session import SESSION_TIMEOUT_SECONDS

JWT_ALGORITHM = "HS256"
COOKIE_NAME = "session"


class SessionClaims(TypedDict):
    email: str
    name: str | None
    picture: str | None
    csrf: str


def mint_session_jwt(
    *,
    jwt_secret: str,
    email: str,
    name: str | None,
    picture: str | None,
) -> str:
    """Mint a signed JWT carrying the identity plus a fresh CSRF token claim.

    Expiry is `SESSION_TIMEOUT_SECONDS` (shared with `app/`, currently 1h), set as the
    standard `exp` claim so `jwt.decode` enforces it server-side automatically — the 1h
    session limit is real, not just a client-side convention, since there is no server-side
    session table to revoke against.
    """
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "email": email,
        "name": name,
        "picture": picture,
        "csrf": csrf_token,
        "iat": now,
        "exp": now + timedelta(seconds=SESSION_TIMEOUT_SECONDS),
    }
    return jwt.encode(
        payload,
        jwt_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_session_jwt(token: str, *, jwt_secret: str) -> SessionClaims:
    """Decode and verify a session JWT. Raises jwt.PyJWTError (or a subclass) on any
    signature, expiry, or malformed-token failure — callers translate that into a 401,
    never leaking the underlying error detail to the client."""
    payload = jwt.decode(
        token,
        jwt_secret,
        algorithms=[JWT_ALGORITHM],
    )
    return SessionClaims(
        email=payload["email"],
        name=payload.get("name"),
        picture=payload.get("picture"),
        csrf=payload["csrf"],
    )


# Re-exported so callers needing the raw seconds value (e.g. cookie max_age) don't import
# core.auth_session directly, keeping the "reuse SESSION_TIMEOUT_SECONDS, don't hardcode
# 3600" rule enforced from one place.
SESSION_MAX_AGE_SECONDS = SESSION_TIMEOUT_SECONDS
