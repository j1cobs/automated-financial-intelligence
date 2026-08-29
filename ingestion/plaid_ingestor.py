from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import requests

from ingestion.base import BaseIngestor, IngestResult

LOGGER = logging.getLogger(__name__)

_MAX_SYNC_ERROR_RETRIES = 5

_NORMALIZED_COLUMNS = [
    "transaction_id",
    "date",
    "description",
    "amount",
    "balance",
    "account_key",
    "account_name",
    "source",
    "pending",
    "pending_transaction_id",
    "merchant_name",
    "pfc_primary",
    "pfc_detailed",
    "pfc_confidence",
]


@dataclass
class SyncResult:
    added: pd.DataFrame  # same normalized columns as IngestResult produces
    modified: pd.DataFrame  # same shape
    removed_ids: list[str]  # Plaid transaction_ids to delete — union of Plaid's removed[] and
    # every non-null pending_transaction_id seen on added/modified rows
    duplicate_accounts_skipped: int
    full_refresh: bool  # True iff EVERY configured token started this run from a null/absent cursor
    cursors: dict[str, str]  # token_fingerprint (sha256 hex of the access token) -> next_cursor


class PlaidIngestor(BaseIngestor):
    def __init__(
        self,
        client_id: str,
        secret: str,
        access_tokens: list[str],
        base_url: str = "https://sandbox.plaid.com",
        timeout_seconds: int = 30,
    ) -> None:
        self.client_id = client_id
        self.secret = secret
        self.access_tokens = access_tokens
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        # Scoped to this instance's lifetime (one PlaidIngestor per run_pipeline() call, per
        # _build_ingestor) -- both _claim_accounts and fetch_accounts need the same /accounts/get
        # data for every token in a run, so this cache turns two Plaid API calls per token per
        # run into one. Keyed on the raw response's "accounts" list, before owner_name is baked
        # in, since the two callers pass different owner_name values ("" vs. the real owner).
        self._raw_accounts_cache: dict[str, list[dict[str, Any]]] = {}

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/{endpoint}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            try:
                body = response.json()
                LOGGER.error(
                    "Plaid error response: status=%s error_type=%s error_code=%s",
                    response.status_code,
                    body.get("error_type"),
                    body.get("error_code"),
                )
            except ValueError:
                LOGGER.error("Plaid error response: status=%s (non-JSON body)", response.status_code)
        response.raise_for_status()
        return response.json()

    def _fetch_accounts_raw(self, access_token: str, owner_name: str) -> list[dict[str, Any]]:
        raw_accounts = self._raw_accounts_cache.get(access_token)
        if raw_accounts is None:
            data = self._post(
                "accounts/get",
                {
                    "client_id": self.client_id,
                    "secret": self.secret,
                    "access_token": access_token,
                },
            )
            raw_accounts = data.get("accounts", [])
            self._raw_accounts_cache[access_token] = raw_accounts

        results = []
        for a in raw_accounts:
            balances = a.get("balances", {})
            mask = a.get("mask")
            name = a.get("name", "")
            results.append(
                {
                    "account_key": f"plaid:{a['account_id']}",
                    "account_name": f"{name} (••••{mask})" if mask else name,
                    "owner_name": owner_name or None,
                    "official_name": a.get("official_name"),
                    "account_type": a.get("type"),
                    "account_subtype": a.get("subtype"),
                    "persistent_account_id": a.get("persistent_account_id"),
                    "mask": mask,
                    "balance_available": balances.get("available"),
                    "balance_current": balances.get("current"),
                    "balance_limit": balances.get("limit"),
                    "iso_currency_code": balances.get("iso_currency_code"),
                    "source": "plaid",
                    "_account_id": a["account_id"],
                }
            )
        return results

    def fetch_accounts(self, owner_by_token: dict[str, str] | None = None) -> list[dict[str, Any]]:
        owner_by_token = owner_by_token or {}
        all_accounts: list[dict[str, Any]] = []
        for token in self.access_tokens:
            try:
                accounts = self._fetch_accounts_raw(token, owner_by_token.get(token, ""))
                all_accounts.extend(accounts)
            except requests.RequestException as error:
                LOGGER.error(
                    "Failed to fetch accounts for token suffix=%s (%s)",
                    token[-6:],
                    type(error).__name__,
                )
                raise
        return all_accounts

    def _request_page(
        self,
        access_token: str,
        start_date: date,
        end_date: date,
        offset: int,
        count: int = 100,
    ) -> dict:
        return self._post(
            "transactions/get",
            {
                "client_id": self.client_id,
                "secret": self.secret,
                "access_token": access_token,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "options": {"count": count, "offset": offset},
            },
        )

    @staticmethod
    def _account_identity(account: dict[str, Any]) -> tuple[str, str, str, str] | None:
        """The identity that decides whether two Plaid accounts are the same real account.

        Deliberately the same tuple `DatabaseClient.canonicalize_account_keys` matches on —
        (official_name, account_subtype, account_type, mask) — so the ingestor and the
        database agree on what "the same account" means. Returns None when any field is
        missing, because a partial tuple cannot distinguish two accounts safely.
        """
        fields = (
            account.get("official_name"),
            account.get("account_subtype"),
            account.get("account_type"),
            account.get("mask"),
        )
        if any(value is None or value == "" for value in fields):
            return None
        return (str(fields[0]), str(fields[1]), str(fields[2]), str(fields[3]))

    @staticmethod
    def _normalize(transaction: dict[str, Any], account_map: dict[str, tuple[str, str]]) -> dict:
        """Normalize one raw Plaid transaction into the shared row shape.

        Shared by both `fetch_transactions` (`/transactions/get`) and `sync_transactions`
        (`/transactions/sync`). `pending` and `pending_transaction_id` are kept as-is (None
        if absent) — do not coerce `pending` to a bool with a default of False, since NULL vs
        FALSE has a specific meaning downstream (NULL = "status unknown", used by
        pre-sync-migration rows). `merchant_name`, `pfc_primary`, `pfc_detailed`, and
        `pfc_confidence` follow the same rule: absent stays None, never a coerced default.
        """
        account_id = transaction.get("account_id", "unknown")
        account_key, account_name = account_map.get(account_id, (f"plaid:{account_id}", account_id))
        pfc = transaction.get("personal_finance_category") or {}
        return {
            "transaction_id": transaction.get("transaction_id", ""),
            "date": pd.to_datetime(transaction.get("date"), errors="coerce").date(),
            "description": transaction.get("name", ""),
            "amount": float(transaction.get("amount", 0.0)),
            "balance": pd.NA,
            "account_key": account_key,
            "account_name": account_name,
            "source": "plaid",
            "pending": transaction.get("pending"),
            "pending_transaction_id": transaction.get("pending_transaction_id"),
            "merchant_name": transaction.get("merchant_name"),
            "pfc_primary": pfc.get("primary"),
            "pfc_detailed": pfc.get("detailed"),
            "pfc_confidence": pfc.get("confidence_level"),
        }

    def _claim_accounts(
        self,
        access_token: str,
        claimed_identities: dict[tuple[str, str, str, str], str],
    ) -> tuple[dict[str, tuple[str, str]], set[str], int]:
        """Claim each real account behind `access_token` for the first token to reveal it.

        A jointly-held account can be exposed by more than one Plaid Item, and each Item
        issues its own account_id *and* its own transaction_ids for the same real
        transactions. `DatabaseClient.canonicalize_account_keys` merges those accounts into
        one account_key, so without this guard the same transactions land twice on it.
        Claim each real account for the first token (in self.access_tokens order, so the
        winner is deterministic) that reveals it, and skip it for every later token. The
        identity tuple must match the one the DB canonicalizes on. `claimed_identities` is
        mutated in place so the claim persists across calls for later tokens.
        """
        try:
            raw_accounts = self._fetch_accounts_raw(access_token, "")
        except requests.RequestException:
            LOGGER.warning(
                "Could not fetch account metadata for token suffix=%s; falling back to account_id",
                access_token[-6:],
            )
            raw_accounts = []

        account_map = {a["_account_id"]: (a["account_key"], a["account_name"]) for a in raw_accounts}

        skipped_account_ids: set[str] = set()
        duplicate_accounts_skipped = 0
        for account in raw_accounts:
            identity = self._account_identity(account)
            # A partially-populated identity is not reliable enough to call two accounts
            # the same, so such accounts are always ingested rather than skipped.
            if identity is None:
                continue
            account_id = account["_account_id"]
            claimed_by = claimed_identities.get(identity)
            if claimed_by is None:
                claimed_identities[identity] = account_id
            elif claimed_by != account_id:
                skipped_account_ids.add(account_id)
                duplicate_accounts_skipped += 1

        return account_map, skipped_account_ids, duplicate_accounts_skipped

    def fetch_transactions(self, start_date: date, end_date: date) -> IngestResult:
        if not self.access_tokens:
            raise ValueError("At least one PLAID_ACCESS_TOKEN must be configured")

        records: list[dict] = []
        duplicate_accounts_skipped = 0
        claimed_identities: dict[tuple[str, str, str, str], str] = {}
        for access_token in self.access_tokens:
            account_map, skipped_account_ids, skipped_count = self._claim_accounts(
                access_token, claimed_identities
            )
            duplicate_accounts_skipped += skipped_count

            offset = 0
            total = None
            while total is None or offset < total:
                try:
                    payload = self._request_page(access_token, start_date, end_date, offset)
                except requests.RequestException as error:
                    LOGGER.error(
                        "Plaid API request failed for token suffix=%s (%s)",
                        access_token[-6:],
                        type(error).__name__,
                    )
                    raise

                transactions = payload.get("transactions", [])
                total = payload.get("total_transactions", len(transactions))
                for transaction in transactions:
                    account_id = transaction.get("account_id", "unknown")
                    if account_id in skipped_account_ids:
                        continue
                    records.append(self._normalize(transaction, account_map))
                offset += len(transactions)
                if not transactions:
                    break

        if not records:
            empty = pd.DataFrame(columns=_NORMALIZED_COLUMNS)
            return IngestResult(empty, duplicate_accounts_skipped)
        return IngestResult(pd.DataFrame.from_records(records), duplicate_accounts_skipped)

    def _request_sync_page(self, access_token: str, cursor: str | None) -> dict:
        payload: dict[str, Any] = {
            "client_id": self.client_id,
            "secret": self.secret,
            "access_token": access_token,
        }
        if cursor:
            payload["cursor"] = cursor
        return self._post("transactions/sync", payload)

    def sync_transactions(self, stored_cursors: dict[str, str]) -> SyncResult:
        """Fetch all deltas since the last sync via `/transactions/sync`.

        `stored_cursors` is keyed by `token_fingerprint = sha256(access_token).hexdigest()` —
        the caller (`pipeline/runner.py`) builds it from `DatabaseClient.get_sync_cursors()`.
        A raw access token is never stored or logged here, only its fingerprint.
        """
        if not self.access_tokens:
            raise ValueError("At least one PLAID_ACCESS_TOKEN must be configured")

        added_records: list[dict] = []
        modified_records: list[dict] = []
        removed_ids: set[str] = set()
        duplicate_accounts_skipped = 0
        cursors: dict[str, str] = {}
        every_token_started_null = True
        claimed_identities: dict[tuple[str, str, str, str], str] = {}

        for access_token in self.access_tokens:
            fingerprint = hashlib.sha256(access_token.encode()).hexdigest()
            starting_cursor = stored_cursors.get(fingerprint)
            if starting_cursor:
                every_token_started_null = False

            # Account metadata (for canonicalization/upsert) is fetched separately by the
            # pipeline via fetch_accounts() — this method only needs account_map to resolve
            # account_id -> account_key/account_name on each transaction, so it must not
            # re-fetch the same /accounts data a second time per token.
            account_map, skipped_account_ids, skipped_count = self._claim_accounts(
                access_token, claimed_identities
            )
            duplicate_accounts_skipped += skipped_count

            token_added: list[dict] = []
            token_modified: list[dict] = []
            token_removed: set[str] = set()
            cursor = starting_cursor
            has_more = True
            error_retries = 0
            while has_more:
                try:
                    payload = self._request_sync_page(access_token, cursor)
                except requests.HTTPError as error:
                    error_code = None
                    try:
                        error_code = (
                            error.response.json().get("error_code") if error.response is not None else None
                        )
                    except ValueError:
                        error_code = None

                    if error_code in (
                        "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION",
                        "PAGINATION_INVALID_CURSOR",
                    ):
                        error_retries += 1
                        if error_retries > _MAX_SYNC_ERROR_RETRIES:
                            LOGGER.error(
                                "Plaid sync for token suffix=%s failed %d times in a row (%s); "
                                "giving up rather than retrying forever",
                                access_token[-6:],
                                error_retries,
                                error_code,
                            )
                            raise

                    if error_code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                        LOGGER.warning(
                            "Plaid sync mutated during pagination for token suffix=%s; "
                            "discarding partial page set and restarting from last saved cursor",
                            access_token[-6:],
                        )
                        token_added = []
                        token_modified = []
                        token_removed = set()
                        cursor = starting_cursor
                        continue
                    if error_code == "PAGINATION_INVALID_CURSOR":
                        # Deliberately do NOT re-evaluate every_token_started_null here. This token
                        # will now fetch from the start (cursor = None), but if it had a cursor at the
                        # time of the error, every_token_started_null remains False. Skipping
                        # reconciliation for this run (rather than misapplying it against a partial
                        # delta) is the fail-safe outcome; a later full-refresh run will reconcile.
                        LOGGER.warning(
                            "Plaid sync cursor invalid for token suffix=%s; resetting to full refresh",
                            access_token[-6:],
                        )
                        token_added = []
                        token_modified = []
                        token_removed = set()
                        cursor = None
                        starting_cursor = None
                        continue

                    LOGGER.error(
                        "Plaid sync request failed for token suffix=%s (%s)",
                        access_token[-6:],
                        type(error).__name__,
                    )
                    raise
                except requests.RequestException as error:
                    LOGGER.error(
                        "Plaid sync request failed for token suffix=%s (%s)",
                        access_token[-6:],
                        type(error).__name__,
                    )
                    raise

                for transaction in payload.get("added", []):
                    account_id = transaction.get("account_id", "unknown")
                    if account_id in skipped_account_ids:
                        continue
                    token_added.append(self._normalize(transaction, account_map))
                for transaction in payload.get("modified", []):
                    account_id = transaction.get("account_id", "unknown")
                    if account_id in skipped_account_ids:
                        continue
                    token_modified.append(self._normalize(transaction, account_map))
                for removed in payload.get("removed", []):
                    removed_id = removed.get("transaction_id")
                    if removed_id:
                        token_removed.add(removed_id)

                has_more = bool(payload.get("has_more"))
                cursor = payload.get("next_cursor", cursor)

            for row in token_added + token_modified:
                pending_id = row.get("pending_transaction_id")
                if pending_id:
                    token_removed.add(pending_id)

            added_records.extend(token_added)
            modified_records.extend(token_modified)
            removed_ids |= token_removed
            if cursor:
                cursors[fingerprint] = cursor

        added_df = (
            pd.DataFrame.from_records(added_records)
            if added_records
            else pd.DataFrame(columns=_NORMALIZED_COLUMNS)
        )
        modified_df = (
            pd.DataFrame.from_records(modified_records)
            if modified_records
            else pd.DataFrame(columns=_NORMALIZED_COLUMNS)
        )

        return SyncResult(
            added=added_df,
            modified=modified_df,
            removed_ids=sorted(removed_ids),
            duplicate_accounts_skipped=duplicate_accounts_skipped,
            full_refresh=every_token_started_null,
            cursors=cursors,
        )
