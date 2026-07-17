from __future__ import annotations

import logging
from datetime import date
from typing import Any
from urllib import response

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

    def _fetch_accounts_raw(
        self, access_token: str, owner_name: str
    ) -> list[dict[str, Any]]:
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

    def fetch_accounts(
        self, owner_by_token: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        owner_by_token = owner_by_token or {}
        all_accounts: list[dict[str, Any]] = []
        for token in self.access_tokens:
            try:
                accounts = self._fetch_accounts_raw(
                    token, owner_by_token.get(token, "")
                )
                all_accounts.extend(accounts)
            except requests.RequestException:
                LOGGER.exception(
                    "Failed to fetch accounts for token suffix=%s", token[-6:]
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

    def fetch_transactions(self, start_date: date, end_date: date) -> pd.DataFrame:
        if not self.access_tokens:
            raise ValueError("At least one PLAID_ACCESS_TOKEN must be configured")

        records: list[dict] = []
        for access_token in self.access_tokens:
            try:
                raw_accounts = self._fetch_accounts_raw(access_token, "")
            except requests.RequestException:
                LOGGER.warning(
                    "Could not fetch account metadata for token suffix=%s; falling back to account_id",
                    access_token[-6:],
                )
                raw_accounts = []

            account_map = {
                a["_account_id"]: (a["account_key"], a["account_name"])
                for a in raw_accounts
            }

            offset = 0
            total = None
            while total is None or offset < total:
                try:
                    payload = self._request_page(
                        access_token, start_date, end_date, offset
                    )
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
                    account_key, account_name = account_map.get(
                        account_id, (f"plaid:{account_id}", account_id)
                    )
                    records.append(
                        {
                            "transaction_id": transaction.get("transaction_id", ""),
                            "date": pd.to_datetime(
                                transaction.get("date"), errors="coerce"
                            ).date(),
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
