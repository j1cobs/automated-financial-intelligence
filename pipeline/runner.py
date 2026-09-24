from __future__ import annotations

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

import pandas as pd
import psycopg

from app.dashboard import _enrich_transactions, load_financial_data

from analytics.models import build_models
from analytics.anomalies import detect_anomalies, suppress_dismissed
from analytics.recurring import derive_streams
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
    status: str
    failed_accounts_summary: str | None


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


def _load_enriched_history(database: DatabaseClient) -> pd.DataFrame:
    """Every persisted transaction, enriched, for the post-persistence passes.

    **Not the frame the pipeline just ingested.** After the first run,
    `sync_transactions` returns a DELTA -- often a handful of rows, sometimes
    none. Recurring detection needs at least two occurrences of a merchant to
    see a cadence, and anomaly detection needs three complete months of
    baseline, so both are structurally incapable of working on a delta: they
    would return nothing every day forever while their unit tests passed.

    Reuses the frozen `load_financial_data` + `_enrich_transactions` rather
    than re-deriving `month`/`tx_type`/`adjusted_amount` here. That also
    supplies `transaction_hash`, which `PlaidIngestor._normalize` does not
    produce (the hash is computed inside `upsert_transactions`) and which the
    `is_outlier` shim needs to flag anything at all.
    """
    tx_df, _acct_df = load_financial_data(database.database_url)
    if tx_df is None or tx_df.empty:
        return pd.DataFrame()
    enriched = _enrich_transactions(tx_df)
    # Duplicate-flagged rows are excluded from analytics everywhere else; an
    # anomaly built on a known double-post would be an artefact.
    return enriched[~enriched["is_duplicate"].fillna(False).astype(bool)]


def _detect_and_store_anomalies(
    database: DatabaseClient,
    history: pd.DataFrame,
    streams: list[dict],
) -> None:
    """Detect anomalies for the current month, persist them, and refresh the
    legacy `is_outlier` flags the frozen Streamlit dashboard still reads."""
    if history is None or history.empty:
        return

    period = date.today().strftime("%Y-%m")
    found = detect_anomalies(history, streams, period)
    found = suppress_dismissed(found, database.get_anomaly_feedback())

    database.upsert_anomalies(
        [{k: v for k, v in row.items() if k != "contributing_hashes"} for row in found]
    )

    # Compatibility shim, not a feature -- see DatabaseClient.set_outlier_flags.
    hashes: list[str] = []
    for row in found:
        hashes.extend(row.get("contributing_hashes", []))
    database.set_outlier_flags(sorted(set(hashes)))

    LOGGER.info("Anomaly detection: %d active anomal%s.", len(found), "y" if len(found) == 1 else "ies")


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
    accounts, accounts_failed = ingestor.fetch_accounts(owner_by_token)

    # Compute union of failed tokens from both sync and accounts-fetch operations
    failed_fingerprints = set(result.failed_tokens) | set(accounts_failed)

    # Build a label map for human-readable error reporting
    label_by_fingerprint = {
        hashlib.sha256(token.encode()).hexdigest(): (owner_by_token.get(token) or f"token …{token[-6:]}")
        for token in settings.plaid_access_tokens
    }

    # Build failed_accounts_summary for logging and persistence
    failed_accounts_summary: str | None = None
    if failed_fingerprints:
        total_tokens = len(settings.plaid_access_tokens)
        reasons = {**accounts_failed, **result.failed_tokens}  # sync_transactions reason wins if both failed
        details = "; ".join(
            f"{label_by_fingerprint.get(fp, fp[:8])} ({reasons.get(fp, 'unknown error')})"
            for fp in sorted(failed_fingerprints)
        )
        failed_accounts_summary = f"{len(failed_fingerprints)}/{total_tokens} accounts failed: {details}"

    # Filter accounts to drop any entry from failed tokens and strip _token_fingerprint key
    accounts = [a for a in accounts if a.get("_token_fingerprint") not in failed_fingerprints]
    for account in accounts:
        account.pop("_token_fingerprint", None)

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

    # Filter out transactions from failed tokens and strip _token_fingerprint column
    if "_token_fingerprint" in transactions.columns:
        transactions = transactions[~transactions["_token_fingerprint"].isin(failed_fingerprints)]
        transactions = transactions.drop(columns=["_token_fingerprint"])

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

    # Step 6b: detect recurring streams (Phase 30). Derived from our own history rather than
    # Plaid's add-on; `scripts/probe_plaid_recurring.py` reports whether the entitlement exists,
    # and `PlaidIngestor.fetch_recurring_streams` can take over without changing this table's
    # shape. Failing here must not fail the run: streams are an enrichment, and the
    # transactions they are derived from are already committed above.
    # Both passes below read PERSISTED history, never `transactions` -- that is
    # the sync delta after the first run, and neither detector can see a cadence
    # or a baseline in one day's rows.
    streams: list[dict] = []
    try:
        history = _load_enriched_history(database)
        streams = derive_streams(history)
        if streams:
            database.upsert_recurring_streams(streams)
    except Exception as error:  # noqa: BLE001 - enrichment must not sink the pipeline
        history = pd.DataFrame()
        LOGGER.warning("Recurring-stream detection skipped: %s", type(error).__name__)

    # Step 6c: anomaly detection (Phase 34). Same reasoning as streams -- an enrichment over
    # already-committed rows, so a failure here is logged and the run still succeeds. Nothing
    # transaction-identifying is logged: only the exception class, per the scrubbed-logging
    # rule that applies to everything the daily pipeline prints.
    try:
        _detect_and_store_anomalies(database, history, streams)
    except Exception as error:  # noqa: BLE001 - enrichment must not sink the pipeline
        LOGGER.warning("Anomaly detection skipped: %s", type(error).__name__)

    # Step 7: advance each Item's cursor only after every write above (upsert, delete, and any
    # reconcile) has committed. Advancing earlier would mean a crash between here and the writes
    # loses that delta permanently, since sync never replays a delta once its cursor is passed.
    for fingerprint, cursor in result.cursors.items():
        if fingerprint not in failed_fingerprints:
            database.set_sync_cursor(fingerprint, cursor)

    # Compute overall status
    total_tokens = len(settings.plaid_access_tokens)
    if not failed_fingerprints:
        status = "success"
    elif len(failed_fingerprints) >= total_tokens:
        status = "failed"
    else:
        status = "partial_success"

    return PipelineResult(
        transactions,
        inserted,
        updated,
        removed,
        result.duplicate_accounts_skipped,
        removed_count,
        result.full_refresh,
        status,
        failed_accounts_summary,
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

    if result.status == "success":
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
    elif result.status == "partial_success":
        LOGGER.warning("Pipeline run: partial success (%s)", result.failed_accounts_summary)
        database.log_pipeline_run(
            started_at,
            "partial_success",
            transactions_inserted=result.inserted,
            transactions_updated=result.updated,
            stale_duplicates_removed=result.removed,
            duplicate_accounts_skipped=result.duplicate_accounts_skipped,
            removed_count=result.removed_count,
            full_refresh=result.full_refresh,
            error_message=(result.failed_accounts_summary or "")[:500],
            trigger_type=trigger_type,
        )
        raise SystemExit(1)
    else:  # "failed" -- every configured token failed
        LOGGER.error("Pipeline run: failed (%s)", result.failed_accounts_summary)
        database.log_pipeline_run(
            started_at,
            "failed",
            error_message=(result.failed_accounts_summary or "")[:500],
            trigger_type=trigger_type,
        )
        raise SystemExit(1)
