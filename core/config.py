from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


def _load_secrets_file(path: Path | None = None) -> dict[str, Any]:
    secrets_path = path or Path(".streamlit/secrets.toml")
    if not secrets_path.exists():
        load_dotenv(dotenv_path=Path(".env"), override=False)
        return {}
    with secrets_path.open("rb") as file:
        return tomllib.load(file)


def _read_value(
    key: str, secrets: dict[str, Any], default: str | None = None
) -> str | None:
    if key in os.environ:
        return os.environ[key]
    if key in secrets:
        value = secrets[key]
        return str(value) if value is not None else None
    return default


def _split_csv(raw_value: str | None) -> list[str]:
    return [item.strip() for item in (raw_value or "").split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    supabase_url: str | None
    google_oauth_client_id: str | None
    google_oauth_client_secret: str | None
    google_oauth_redirect_uri: str | None
    google_allowed_emails: list[str]
    plaid_client_id: str | None
    plaid_secret: str | None
    plaid_access_tokens: list[str]
    plaid_access_token_owners: list[str]
    plaid_base_url: str
    database_url: str
    model_path: str
    labeled_dataset_path: str


def load_settings() -> Settings:
    secrets = _load_secrets_file()

    database_url = _read_value("DATABASE_URL", secrets)
    if not database_url:
        raise ConfigError("DATABASE_URL is required in env vars or secrets.toml")

    google_oauth_client_id = _read_value("GOOGLE_OAUTH_CLIENT_ID", secrets)
    google_oauth_client_secret = _read_value("GOOGLE_OAUTH_CLIENT_SECRET", secrets)
    google_oauth_redirect_uri = _read_value("GOOGLE_OAUTH_REDIRECT_URI", secrets)
    google_allowed_emails = [
        email.lower()
        for email in _split_csv(
            _read_value(
                "GOOGLE_ALLOWED_EMAILS",
                secrets,
            )
        )
    ]

    return Settings(
        supabase_url=_read_value("SUPABASE_URL", secrets),
        google_oauth_client_id=google_oauth_client_id,
        google_oauth_client_secret=google_oauth_client_secret,
        google_oauth_redirect_uri=google_oauth_redirect_uri,
        google_allowed_emails=google_allowed_emails,
        plaid_client_id=_read_value("PLAID_CLIENT_ID", secrets),
        plaid_secret=_read_value("PLAID_SECRET", secrets),
        plaid_access_tokens=_split_csv(_read_value("PLAID_ACCESS_TOKENS", secrets, "")),
        plaid_access_token_owners=_split_csv(
            _read_value("PLAID_ACCESS_TOKEN_OWNERS", secrets, "")
        ),
        plaid_base_url=_read_value(
            "PLAID_BASE_URL", secrets, "https://sandbox.plaid.com"
        )
        or "https://sandbox.plaid.com",
        database_url=database_url,
        model_path=_read_value("MODEL_PATH", secrets, "artifacts/classifier.joblib")
        or "artifacts/classifier.joblib",
        labeled_dataset_path=_read_value(
            "LABELED_DATASET_PATH", secrets, "labeled_transactions.csv"
        )
        or "labeled_transactions.csv",
    )
