from __future__ import annotations

import html
import logging
import secrets
import time

import streamlit as st

from core.auth_session import SESSION_TIMEOUT_SECONDS, is_session_expired
from core.google_oauth import (
    build_authorization_url,
    exchange_code,
    fetch_userinfo,
    generate_pkce_pair,
    is_authorized_identity,
)

LOGGER = logging.getLogger(__name__)

_PENDING_TTL_SECONDS = 600
_PENDING_MAX_ENTRIES = 32
_google_oauth_pending_sessions: dict[str, tuple[str, float]] = {}  # state -> (verifier, created_at)


def _prune_pending_sessions(now: float) -> None:
    expired = [
        state
        for state, (_, created_at) in _google_oauth_pending_sessions.items()
        if now - created_at > _PENDING_TTL_SECONDS
    ]
    for state in expired:
        del _google_oauth_pending_sessions[state]
    while len(_google_oauth_pending_sessions) >= _PENDING_MAX_ENTRIES:
        oldest = min(_google_oauth_pending_sessions, key=lambda s: _google_oauth_pending_sessions[s][1])
        del _google_oauth_pending_sessions[oldest]


def query_param(name: str) -> str | None:
    value = st.query_params.get(name)
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


def clear_query_params() -> None:
    st.query_params.clear()


def sign_out() -> None:
    for key in (
        "authenticated",
        "authenticated_user",
        "authenticated_at",
    ):
        st.session_state.pop(key, None)
    clear_query_params()


def is_authenticated() -> bool:
    if not st.session_state.get("authenticated"):
        return False

    authenticated_at = st.session_state.get("authenticated_at")
    if is_session_expired(authenticated_at, time.time()):
        st.warning("Your session expired. Please sign in again.")
        sign_out()
        return False

    return True


def start_google_sign_in(settings) -> str:
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    _prune_pending_sessions(time.time())
    _google_oauth_pending_sessions[state] = (code_verifier, time.time())
    return build_authorization_url(
        client_id=settings.google_oauth_client_id,
        redirect_uri=settings.google_oauth_redirect_uri,
        state=state,
        code_challenge=code_challenge,
    )


def consume_google_callback(settings) -> bool:
    code = query_param("code")
    state = query_param("state")
    if not code or not state:
        return False

    pending = _google_oauth_pending_sessions.pop(state, None)
    if not pending or (time.time() - pending[1]) > _PENDING_TTL_SECONDS:
        st.error("Google sign-in session expired. Please try again.")
        clear_query_params()
        return False
    code_verifier, _ = pending

    try:
        token_response = exchange_code(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
            code=code,
            code_verifier=code_verifier,
        )
        identity = fetch_userinfo(token_response["access_token"])
    except Exception:
        LOGGER.exception("Google sign-in failed")
        st.error("Google sign-in failed. Please try again.")
        clear_query_params()
        return False

    if not is_authorized_identity(identity, settings.google_allowed_emails):
        st.error("This Google account is not allowed to access the dashboard.")
        clear_query_params()
        return False

    st.session_state.authenticated = True
    st.session_state.authenticated_at = time.time()
    st.session_state.authenticated_user = {
        "email": identity.email,
        "name": identity.name,
        "picture": identity.picture,
        "subject": identity.subject,
    }
    clear_query_params()
    st.rerun()
    return True


def render_sign_in(settings) -> bool:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return is_authenticated()

    if consume_google_callback(settings):
        return True

    st.title("Sign in with Google")
    if (
        not settings.google_oauth_client_id
        or not settings.google_oauth_client_secret
        or not settings.google_oauth_redirect_uri
    ):
        st.error(
            "Configure GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, "
            "and GOOGLE_OAUTH_REDIRECT_URI first."
        )
        return False

    auth_url = start_google_sign_in(settings)
    safe_url = html.escape(auth_url)
    st.html(
        f'''
        <a href="{safe_url}" target="_blank"
           style="display:inline-block;padding:0.5em 1em;background:#4285F4;color:white;
                  border-radius:4px;text-decoration:none;font-family:sans-serif;">
            Continue with Google
        </a>
        '''
    )
    st.caption("Google handles the credential check; the app only accepts allowlisted identities.")
    return False


def render_sidebar(settings) -> None:
    st.sidebar.caption(f"Session timeout: {SESSION_TIMEOUT_SECONDS // 3600} hours")

    if st.session_state.get("authenticated_user"):
        user = st.session_state.authenticated_user
        st.sidebar.caption(f"Signed in as {user.get('email', 'Google user')}")
        if settings.supabase_url:
            st.sidebar.caption(f"Supabase: {settings.supabase_url}")
        if st.sidebar.button("Sign out"):
            sign_out()
            st.rerun()
