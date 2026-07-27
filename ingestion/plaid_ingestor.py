from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd
import requests

from ingestion.base import BaseIngestor

LOGGER = logging.getLogger(__name__)


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

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            f"{self.base_url}/{endpoint}",
            json=payload,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            LOGGER.error("Plaid error response: %s", response.text)
        response.raise_for_status()
        return response.json()

    def _fetch_accounts_raw(self, access_token: str, owner_name: str) -> list[dict[str, Any]]:
        data = self._post(
            "accounts/get",
            {
                "client_id": self.client_id,
                "secret": self.secret,
                "access_token": access_token,
            },
        )
        results = []
        for a in data.get("accounts", []):
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
            except requests.RequestException:
                LOGGER.exception("Failed to fetch accounts for token suffix=%s", token[-6:])
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

    def fetch_transactions(self, start_date: date, end_date: date) -> pd.DataFrame:
        if not self.access_tokens:
            raise ValueError("At least one PLAID_ACCESS_TOKEN must be configured")

        records: list[dict] = []
        # A jointly-held account can be exposed by more than one Plaid Item, and each Item
        # issues its own account_id *and* its own transaction_ids for the same real
        # transactions. `DatabaseClient.canonicalize_account_keys` merges those accounts into
        # one account_key, so without this guard the same transactions land twice on it.
        # Claim each real account for the first token (in self.access_tokens order, so the
        # winner is deterministic) that reveals it, and skip it for every later token. The
        # identity tuple must match the one the DB canonicalizes on.
        claimed_identities: dict[tuple[str, str, str, str], str] = {}
        for access_token in self.access_tokens:
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
                    LOGGER.info(
                        "Skipping duplicate Plaid account mask=%s (account_id=%s) for token "
                        "suffix=%s; already ingested via account_id=%s from an earlier token",
                        account.get("mask"),
                        account_id,
                        access_token[-6:],
                        claimed_by,
                    )

            offset = 0
            total = None
            while total is None or offset < total:
                try:
                    payload = self._request_page(access_token, start_date, end_date, offset)
                except requests.RequestException:
                    LOGGER.exception(
                        "Plaid API request failed for token suffix=%s",
                        access_token[-6:],
                    )
                    raise

                transactions = payload.get("transactions", [])
                total = payload.get("total_transactions", len(transactions))
                for transaction in transactions:
                    account_id = transaction.get("account_id", "unknown")
                    if account_id in skipped_account_ids:
                        continue
                    account_key, account_name = account_map.get(
                        account_id, (f"plaid:{account_id}", account_id)
                    )
                    records.append(
                        {
                            "transaction_id": transaction.get("transaction_id", ""),
                            "date": pd.to_datetime(transaction.get("date"), errors="coerce").date(),
                            "description": transaction.get("name", ""),
                            "amount": float(transaction.get("amount", 0.0)),
                            "balance": pd.NA,
                            "account_key": account_key,
                            "account_name": account_name,
                            "source": "plaid",
                        }
                    )
                offset += len(transactions)
                if not transactions:
                    break

        if not records:
            return pd.DataFrame(
                columns=[
                    "transaction_id",
                    "date",
                    "description",
                    "amount",
                    "balance",
                    "account_key",
                    "account_name",
                    "source",
                ]
            )
        return pd.DataFrame.from_records(records)
