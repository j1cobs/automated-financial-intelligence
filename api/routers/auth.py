"""Google OAuth endpoints for the React frontend: start the PKCE flow, handle Google's
callback, and let the frontend fetch the signed-in identity + CSRF token.

Deliberately has NO `/auth/logout` endpoint (see the R1 plan) — sessions are stateless JWTs
with a 1h expiry and no server-side revocation, so "signing out" client-side wouldn't
actually invalidate anything; building the endpoint would be misleading.
"""

from __future__ import annotations

import logging
import secrets as secrets_module
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from core.google_oauth import (
    build_authorization_url,
    exchange_code,
    fetch_userinfo,
    generate_pkce_pair,
    is_authorized_identity,
)

from ..deps import CurrentUserDep, DbDep, SettingsDep
from ..security import COOKIE_NAME, SESSION_MAX_AGE_SECONDS, mint_session_jwt

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _sign_in_error_redirect(frontend_origin: str) -> RedirectResponse:
    # Generic error indicator only — no failure detail is exposed to the client, matching
    # the repo's existing logging-hygiene standard (PLAN.md Phase 14).
    url = f"{frontend_origin.rstrip('/')}/sign-in?{urlencode({'error': 'oauth_failed'})}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get("/google/start")
def google_start(
    settings: SettingsDep,
    db: DbDep,
) -> RedirectResponse:
    if not settings.google_oauth_client_id or not settings.google_oauth_redirect_uri:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured",
        )

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets_module.token_urlsafe(32)
    db.store_pending_oauth_state(state, code_verifier)

    auth_url = build_authorization_url(
        client_id=settings.google_oauth_client_id,
        redirect_uri=settings.google_oauth_redirect_uri,
        state=state,
        code_challenge=code_challenge,
    )
    return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/google/callback")
def google_callback(
    request: Request,
    settings: SettingsDep,
    db: DbDep,
) -> RedirectResponse:
    frontend_origin = settings.frontend_origin or ""
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code or not state:
        LOGGER.warning("Google OAuth callback missing code or state")
        return _sign_in_error_redirect(frontend_origin)

    code_verifier = db.pop_pending_oauth_state(state)
    if not code_verifier:
        LOGGER.warning("Google OAuth callback with missing/expired pending state")
        return _sign_in_error_redirect(frontend_origin)

    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        LOGGER.error("Google OAuth callback invoked without client credentials configured")
        return _sign_in_error_redirect(frontend_origin)

    try:
        token_response = exchange_code(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri or "",
            code=code,
            code_verifier=code_verifier,
        )
        identity = fetch_userinfo(token_response["access_token"])
    except Exception:
        LOGGER.exception("Google sign-in failed")
        return _sign_in_error_redirect(frontend_origin)

    if not is_authorized_identity(identity, settings.google_allowed_emails):
        LOGGER.warning("Google sign-in rejected: identity not on allowlist")
        return _sign_in_error_redirect(frontend_origin)

    if not settings.jwt_secret:
        LOGGER.error("JWT_SECRET is not configured; cannot mint session")
        return _sign_in_error_redirect(frontend_origin)

    token = mint_session_jwt(
        jwt_secret=settings.jwt_secret,
        email=identity.email,
        name=identity.name,
        picture=identity.picture,
    )

    response = RedirectResponse(url=frontend_origin or "/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    return response


@router.get("/me")
def me(current_user: CurrentUserDep) -> dict:
    return {
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "csrf_token": current_user.csrf,
    }
