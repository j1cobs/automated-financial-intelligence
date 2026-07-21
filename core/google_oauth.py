from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import requests

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    name: str | None
    picture: str | None
    subject: str
    email_verified: bool


def generate_pkce_pair() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "prompt": "select_account",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{GOOGLE_AUTH_ENDPOINT}?{query}"


def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    response = requests.post(
        GOOGLE_TOKEN_ENDPOINT,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_userinfo(access_token: str) -> GoogleIdentity:
    response = requests.get(
        GOOGLE_USERINFO_ENDPOINT,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return GoogleIdentity(
        email=str(payload.get("email", "")).lower(),
        name=payload.get("name"),
        picture=payload.get("picture"),
        subject=str(payload.get("sub", "")),
        email_verified=payload.get("email_verified") in (True, "true"),
    )


def is_authorized_identity(
    identity: GoogleIdentity,
    allowed_emails: list[str],
) -> bool:
    if not identity.email or not identity.email_verified:
        return False

    return identity.email in allowed_emails
