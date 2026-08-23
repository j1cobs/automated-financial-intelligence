from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import pandas as pd
import psycopg

from analytics.placeholders import build_placeholder_models
from core.config import ConfigError, load_settings
from database.db import DatabaseClient
from ingestion.plaid_ingestor import PlaidIngestor

LOGGER = logging.getLogger(__name__)


class PipelineResult(NamedTuple):
    transactions: pd.DataFrame
    inserted: int
    updated: int
    removed: int
    duplicate_accounts_skipped: int


def _build_ingestor(settings):
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise ConfigError("PLAID_CLIENT_ID and PLAID_SECRET are required")
    if not settings.plaid_access_tokens:
        raise ConfigError("PLAID_ACCESS_TOKENS is required")
    if settings.plaid_access_token_owners and len(settings.plaid_access_token_owners) != len(
        settings.plaid_access_tokens
    ):
        raise ConfigError(
            "PLAID_ACCESS_TOKEN_OWNERS must have the same number of entries as PLAID_ACCESS_TOKENS"
        )
    return PlaidIngestor(
        client_id=settings.plaid_client_id,
        secret=settings.plaid_secret,
        access_tokens=settings.plaid_access_tokens,
        base_url=settings.plaid_base_url,
    )


def run_pipeline(days_back: int = 90) -> PipelineResult:
    settings = load_settings()

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    ingestor = _build_ingestor(settings)

    database = DatabaseClient(settings.database_url)
    database.ensure_schema()

    # strict=False is deliberate: plaid_access_token_owners is optional (_build_ingestor only
    # enforces equal length when it's non-empty), so an empty owners list must zip to {} here,
    # not raise.
    owner_by_token = dict(zip(settings.plaid_access_tokens, settings.plaid_access_token_owners, strict=False))
    accounts = ingestor.fetch_accounts(owner_by_token)

    # Re-map each account onto its existing canonical account_key (if any) *before* persisting,
    # so a Plaid Item re-link (new account_ids for the same physical accounts, e.g. after
    # credential rotation) merges into existing history instead of creating a duplicate account.
    key_remap = database.canonicalize_account_keys(accounts)
    for account in accounts:
        account["account_key"] = key_remap.get(account["account_key"], account["account_key"])
    database.upsert_plaid_accounts(accounts)

    transactions, duplicate_accounts_skipped = ingestor.fetch_transactions(
        start_date=start_date, end_date=end_date
    )
    if transactions.empty:
        return PipelineResult(transactions, 0, 0, 0, duplicate_accounts_skipped)
    transactions["account_key"] = transactions["account_key"].map(lambda key: key_remap.get(key, key))

    models = build_placeholder_models()
    transactions["category"] = models.classifier.categorize(transactions["description"])
    transactions = models.outlier_detector.score(transactions)

    database.upsert_categories(transactions["category"].dropna().astype(str).tolist())
    inserted, updated = database.upsert_transactions(transactions)
    # Upserts are append-only: a transaction that acquires a new Plaid transaction_id (e.g. a
    # pending charge that posts, or an account re-linked under a new Item) hashes differently
    # and lands as an extra row alongside its older copy. Reconciling this window against what
    # Plaid just returned trims those stale leftovers. Must run after upsert_transactions, and
    # on the frame whose account_key has already been remapped through key_remap above.
    removed = database.reconcile_transactions(transactions, start_date, end_date)
    return PipelineResult(transactions, inserted, updated, removed, duplicate_accounts_skipped)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    started_at = datetime.now(UTC)
    database = None
    try:
        settings = load_settings()
        database = DatabaseClient(settings.database_url)
    except ConfigError:
        LOGGER.exception("Pipeline failed")
        raise
    trigger_type = settings.github_event_name or "local"

    try:
        result = run_pipeline()
    except psycopg.OperationalError as error:
        database.log_pipeline_run(
            started_at, "failed", error_class=type(error).__name__, trigger_type=trigger_type
        )
        LOGGER.error("Pipeline run: failed (database connection error)")
        raise SystemExit(1) from None
    except Exception as error:
        database.log_pipeline_run(
            started_at,
            "failed",
            error_class=type(error).__name__,
            error_message=str(error)[:500],
            trigger_type=trigger_type,
        )
        LOGGER.error("Pipeline run: failed (%s)", type(error).__name__)
        raise

    database.log_pipeline_run(
        started_at,
        "success",
        transactions_inserted=result.inserted,
        transactions_updated=result.updated,
        stale_duplicates_removed=result.removed,
        duplicate_accounts_skipped=result.duplicate_accounts_skipped,
        trigger_type=trigger_type,
    )
    LOGGER.info("Pipeline run: success")
