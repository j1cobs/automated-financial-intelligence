from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


def _load_secrets_file(path: Path | None = None) -> dict[str, Any]:
    secrets_path = path or Path(".streamlit/secrets.toml")
    if not secrets_path.exists():
        return {}
    with secrets_path.open("rb") as file:
        return tomllib.load(file)


def _read_value(key: str, secrets: dict[str, Any], default: str | None = None) -> str | None:
    if key in os.environ:
        return os.environ[key]
    if key in secrets:
        value = secrets[key]
        return str(value) if value is not None else None
    return default


@dataclass(frozen=True)
class Settings:
    ingestion_source: str
    plaid_client_id: str | None
    plaid_secret: str | None
    plaid_access_tokens: list[str]
    plaid_base_url: str
    csv_paths: list[str]
    database_url: str
    model_path: str
    labeled_dataset_path: str
    dashboard_allowed_emails: list[str]
    dashboard_password: str | None



def load_settings() -> Settings:
    secrets = _load_secrets_file()
    database_url = _read_value("DATABASE_URL", secrets)
    if not database_url:
        raise ConfigError("DATABASE_URL is required in env vars or secrets.toml")

    access_tokens = _read_value("PLAID_ACCESS_TOKENS", secrets, "") or ""
    csv_paths = _read_value("CSV_PATHS", secrets, "") or ""

    allowed_emails = _read_value("ALLOWED_EMAILS", secrets, "") or ""

    return Settings(
        ingestion_source=(_read_value("INGESTION_SOURCE", secrets, "csv") or "csv").lower(),
        plaid_client_id=_read_value("PLAID_CLIENT_ID", secrets),
        plaid_secret=_read_value("PLAID_SECRET", secrets),
        plaid_access_tokens=[token.strip() for token in access_tokens.split(",") if token.strip()],
        plaid_base_url=_read_value("PLAID_BASE_URL", secrets, "https://sandbox.plaid.com") or "https://sandbox.plaid.com",
        csv_paths=[path.strip() for path in csv_paths.split(",") if path.strip()],
        database_url=database_url,
        model_path=_read_value("MODEL_PATH", secrets, "artifacts/classifier.joblib") or "artifacts/classifier.joblib",
        labeled_dataset_path=_read_value("LABELED_DATASET_PATH", secrets, "labeled_transactions.csv") or "labeled_transactions.csv",
        dashboard_allowed_emails=[email.strip().lower() for email in allowed_emails.split(",") if email.strip()],
        dashboard_password=_read_value("DASHBOARD_PASSWORD", secrets),
    )
