from __future__ import annotations

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


def query_param(name: str) -> str | None:
    values = st.experimental_get_query_params().get(name)
    if not values:
        return None
    return values[0]


def clear_query_params() -> None:
    st.experimental_set_query_params()


def sign_out() -> None:
    for key in (
        "authenticated",
        "authenticated_user",
        "authenticated_at",
        "google_oauth_state",
        "google_oauth_code_verifier",
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
    st.session_state.google_oauth_state = state
    st.session_state.google_oauth_code_verifier = code_verifier
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

    expected_state = st.session_state.get("google_oauth_state")
    code_verifier = st.session_state.get("google_oauth_code_verifier")
    if not expected_state or not code_verifier:
        st.error("Google sign-in session expired. Please try again.")
        clear_query_params()
        return False

    if state != expected_state:
        st.error("Google sign-in state check failed.")
        clear_query_params()
        return False

    try:
        token_response = exchange_code(
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            redirect_uri=settings.google_oauth_redirect_uri,
            code=code,
            code_verifier=code_verifier,
        )
        identity = fetch_userinfo(token_response["access_token"])
    except Exception as error:
        st.error(f"Google sign-in failed: {error}")
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
    st.session_state.pop("google_oauth_state", None)
    st.session_state.pop("google_oauth_code_verifier", None)
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
            "Configure GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI first."
        )
        return False

    auth_url = start_google_sign_in(settings)
    st.markdown(f"[Continue with Google]({auth_url})")
    st.caption(
        "Google handles the credential check; the app only accepts allowlisted identities."
    )
    return False


def render_sidebar(settings) -> None:
    if settings.supabase_url:
        st.sidebar.caption(f"Supabase: {settings.supabase_url}")
    st.sidebar.caption(f"Session timeout: {SESSION_TIMEOUT_SECONDS // 3600} hours")

    if st.session_state.get("authenticated_user"):
        user = st.session_state.authenticated_user
        st.sidebar.caption(f"Signed in as {user.get('email', 'Google user')}")
        if st.sidebar.button("Sign out"):
            sign_out()
            st.rerun()
