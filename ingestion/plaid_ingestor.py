from __future__ import annotations

import logging
from datetime import date

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

    def _request_page(self, access_token: str, start_date: date, end_date: date, offset: int, count: int = 100) -> dict:
        payload = {
            "client_id": self.client_id,
            "secret": self.secret,
            "access_token": access_token,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "options": {"count": count, "offset": offset},
        }
        response = requests.post(
            f"{self.base_url}/transactions/get",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def fetch_transactions(self, start_date: date, end_date: date) -> pd.DataFrame:
        if not self.access_tokens:
            raise ValueError("At least one PLAID_ACCESS_TOKEN must be configured")

        records: list[dict] = []
        for access_token in self.access_tokens:
            offset = 0
            total = None
            while total is None or offset < total:
                try:
                    payload = self._request_page(access_token, start_date, end_date, offset)
                except requests.RequestException:
                    LOGGER.exception("Plaid API request failed for token suffix=%s", access_token[-6:])
                    raise

                transactions = payload.get("transactions", [])
                total = payload.get("total_transactions", len(transactions))
                for transaction in transactions:
                    records.append(
                        {
                            "transaction_id": transaction.get("transaction_id", ""),
                            "date": pd.to_datetime(transaction.get("date"), errors="coerce").date(),
                            "description": transaction.get("name", ""),
                            "amount": float(transaction.get("amount", 0.0)),
                            "balance": pd.NA,
                            "account_name": transaction.get("account_id", "unknown"),
                            "source": "plaid",
                        }
                    )
                offset += len(transactions)
                if not transactions:
                    break

        if not records:
            return pd.DataFrame(columns=["transaction_id", "date", "description", "amount", "balance", "account_name", "source"])
        return pd.DataFrame.from_records(records)
