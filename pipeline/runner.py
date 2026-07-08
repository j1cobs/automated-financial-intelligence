from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from analytics.placeholders import build_placeholder_models
from core.config import ConfigError, load_settings
from database.db import DatabaseClient
from ingestion.plaid_ingestor import PlaidIngestor

LOGGER = logging.getLogger(__name__)


def _build_ingestor(settings):
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise ConfigError("PLAID_CLIENT_ID and PLAID_SECRET are required")
    if not settings.plaid_access_tokens:
        raise ConfigError("PLAID_ACCESS_TOKENS is required")
    if settings.plaid_access_token_owners and len(
        settings.plaid_access_token_owners
    ) != len(settings.plaid_access_tokens):
        raise ConfigError(
            "PLAID_ACCESS_TOKEN_OWNERS must have the same number of entries as PLAID_ACCESS_TOKENS"
        )
    return PlaidIngestor(
        client_id=settings.plaid_client_id,
        secret=settings.plaid_secret,
        access_tokens=settings.plaid_access_tokens,
        base_url=settings.plaid_base_url,
    )


def run_pipeline(days_back: int = 90) -> pd.DataFrame:
    settings = load_settings()

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    ingestor = _build_ingestor(settings)
    transactions = ingestor.fetch_transactions(start_date=start_date, end_date=end_date)
    if transactions.empty:
        LOGGER.info("No transactions fetched. Pipeline complete.")
        return transactions

    models = build_placeholder_models()
    transactions["category"] = models.classifier.categorize(transactions["description"])
    transactions = models.outlier_detector.score(transactions)

    database = DatabaseClient(settings.database_url)
    database.ensure_schema()

    owner_by_token = dict(zip(settings.plaid_access_tokens, settings.plaid_access_token_owners))
    accounts = ingestor.fetch_accounts(owner_by_token)
    database.upsert_plaid_accounts(accounts)

    database.upsert_categories(transactions["category"].dropna().astype(str).tolist())
    database.upsert_transactions(transactions)
    LOGGER.info("Pipeline completed successfully")
    return transactions


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    try:
        run_pipeline()
    except Exception:
        LOGGER.exception("Pipeline failed")
        raise
