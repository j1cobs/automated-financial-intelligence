"""FastAPI dependency-injection wrappers around the existing `core.config.load_settings()`
and `database.db.DatabaseClient` — no new config/DB logic lives here, just the wiring FastAPI
needs to hand each request a `Settings` instance, a `DatabaseClient`, and (for authenticated
routes) the caller's verified identity.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status

from core.config import Settings, load_settings
from database.db import DatabaseClient

from .security import COOKIE_NAME, decode_session_jwt


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are process-wide and immutable once loaded, so cache the single instance
    rather than re-reading env/secrets.toml on every request."""
    return load_settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db(settings: SettingsDep) -> DatabaseClient:
    return DatabaseClient(settings.database_url)


DbDep = Annotated[DatabaseClient, Depends(get_db)]


@dataclass(frozen=True)
class CurrentUser:
    email: str
    name: str | None
    picture: str | None
    csrf: str


def get_current_user(
    request: Request,
    settings: SettingsDep,
) -> CurrentUser:
    """Validate the session JWT cookie and return the signed-in identity, or raise 401.

    Never leaks *why* validation failed (expired vs. tampered vs. missing) to the client —
    all three collapse to the same generic 401, per the repo's logging-hygiene standard of
    not exposing internals. `settings.jwt_secret` missing entirely is a server
    misconfiguration, not a client error, so it also 401s rather than 500ing with a stack
    trace that could leak into a response.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token or not settings.jwt_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        claims = decode_session_jwt(token, jwt_secret=settings.jwt_secret)
    except jwt.PyJWTError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated") from error

    return CurrentUser(
        email=claims["email"],
        name=claims["name"],
        picture=claims["picture"],
        csrf=claims["csrf"],
    )


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def require_csrf(request: Request, current_user: CurrentUserDep) -> None:
    """Shared double-submit CSRF check for every write endpoint (R2's 5 write paths,
    and any future ones) — see the R1 plan's CSRF section. The session JWT carries a
    `csrf` claim minted at sign-in (`security.mint_session_jwt`); the frontend echoes
    it back via the `X-CSRF-Token` header on every non-GET request. A cookie alone
    auto-attaches to any cross-site request, so this header is what a bare cross-site
    form/fetch cannot forge. `secrets.compare_digest` avoids a timing side-channel on
    the comparison. Deliberately one shared dependency rather than per-endpoint
    copy-pasted logic, so a future write endpoint can't forget it.
    """
    header_token = request.headers.get("X-CSRF-Token")
    if not header_token or not secrets.compare_digest(header_token, current_user.csrf):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


RequireCsrfDep = Annotated[None, Depends(require_csrf)]
