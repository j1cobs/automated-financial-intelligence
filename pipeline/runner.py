from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import pandas as pd
import psycopg

from analytics.models import build_models
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
    removed_count: int
    full_refresh: bool


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

    # Step 1-2: resume each Plaid Item's /transactions/sync cursor (or start a full refresh if
    # this Item has never synced) and pull every added/modified/removed transaction since then.
    stored_cursors = database.get_sync_cursors()
    result = ingestor.sync_transactions(stored_cursors)

    # strict=False is deliberate: plaid_access_token_owners is optional (_build_ingestor only
    # enforces equal length when it's non-empty), so an empty owners list must zip to {} here,
    # not raise.
    owner_by_token = dict(zip(settings.plaid_access_tokens, settings.plaid_access_token_owners, strict=False))
    accounts = ingestor.fetch_accounts(owner_by_token)

    # Re-map each account onto its existing canonical account_key (if any) *before* persisting,
    # so a Plaid Item re-link (new account_ids for the same physical accounts, e.g. after
    # credential rotation) merges into existing history instead of creating a duplicate account.
    # Unchanged by the sync migration (Phase 17) -- account discovery/canonicalization is
    # independent of how transactions are fetched.
    key_remap = database.canonicalize_account_keys(accounts)
    for account in accounts:
        account["account_key"] = key_remap.get(account["account_key"], account["account_key"])
    database.upsert_plaid_accounts(accounts)
    database.record_balance_snapshots(accounts)

    # Step 3-4: combine this run's added + modified rows into one frame and remap their
    # account_keys through the same key_remap used above, so sync-sourced rows land on the
    # same canonical account_key as the accounts block just persisted.
    transactions = pd.concat([result.added, result.modified], ignore_index=True)
    transactions["account_key"] = transactions["account_key"].map(lambda key: key_remap.get(key, key))

    models = build_models(settings.categorizer_mode)
    if settings.categorizer_mode == "cascade":
        # CascadeCategorizer.categorize takes the whole frame (it needs pfc_primary and
        # merchant_name, not just description) plus the merchant-memory lookup, and it sets
        # both `category` and `category_source` on the returned frame itself.
        merchant_lookup = database.get_all_merchant_categories()
        transactions = models.classifier.categorize(transactions, merchant_lookup)
    else:
        # "placeholder" mode's classifier predates the cascade and keeps the old
        # Series-in/Series-out signature (see analytics/placeholders.py).
        transactions["category"] = models.classifier.categorize(transactions["description"])
    transactions = models.outlier_detector.score(transactions)

    database.upsert_categories(transactions["category"].dropna().astype(str).tolist())
    inserted, updated = database.upsert_transactions(transactions)

    # Step 5: Plaid's `removed` (plus superseded pending_transaction_id lineage, already folded
    # in by sync_transactions) is authoritative, so these ids are safe to delete on a delta, not
    # just a full refresh.
    removed_count = database.delete_transactions_by_external_ids(result.removed_ids)

    # Step 6: reconcile_transactions infers duplication from Plaid's per-natural-key counts,
    # which is only sound when `transactions` is everything Plaid currently returns for the
    # window -- true only when every token's sync started from a null cursor. Never call this on
    # a delta (see the IKEA-delta hazard in reconcile_transactions's docstring).
    removed = 0
    if result.full_refresh:
        removed = database.reconcile_transactions(transactions, start_date, end_date, full_refresh=True)

    # Step 7: advance each Item's cursor only after every write above (upsert, delete, and any
    # reconcile) has committed. Advancing earlier would mean a crash between here and the writes
    # loses that delta permanently, since sync never replays a delta once its cursor is passed.
    for fingerprint, cursor in result.cursors.items():
        database.set_sync_cursor(fingerprint, cursor)

    return PipelineResult(
        transactions,
        inserted,
        updated,
        removed,
        result.duplicate_accounts_skipped,
        removed_count,
        result.full_refresh,
    )


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
        removed_count=result.removed_count,
        full_refresh=result.full_refresh,
        trigger_type=trigger_type,
    )
    LOGGER.info("Pipeline run: success")
