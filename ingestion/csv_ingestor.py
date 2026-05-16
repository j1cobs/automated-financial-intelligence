from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion.base import BaseIngestor

LOGGER = logging.getLogger(__name__)

COLUMN_ALIASES = {
    "date": ["date", "transaction_date", "posted_date", "posting_date"],
    "description": ["description", "name", "merchant", "memo"],
    "amount": ["amount", "transaction_amount", "value", "debit", "credit"],
    "balance": ["balance", "running_balance", "available_balance", "current_balance"],
    "account_name": ["account", "account_name", "account_id", "card_name"],
    "transaction_id": ["transaction_id", "id", "fitid", "reference", "unique_id"],
}


class CSVIngestor(BaseIngestor):
    def __init__(self, csv_paths: list[str]) -> None:
        self.csv_paths = [Path(path) for path in csv_paths]

    @staticmethod
    def _find_column(df: pd.DataFrame, canonical_name: str) -> str | None:
        lowered = {column.lower().strip(): column for column in df.columns}
        for alias in COLUMN_ALIASES[canonical_name]:
            if alias in lowered:
                return lowered[alias]
        return None

    def _normalize_frame(self, frame: pd.DataFrame, source_name: str) -> pd.DataFrame:
        date_col = self._find_column(frame, "date")
        description_col = self._find_column(frame, "description")
        amount_col = self._find_column(frame, "amount")
        if not date_col or not description_col or not amount_col:
            raise ValueError(f"CSV '{source_name}' is missing required transaction columns")

        balance_col = self._find_column(frame, "balance")
        account_col = self._find_column(frame, "account_name")
        transaction_id_col = self._find_column(frame, "transaction_id")

        normalized = pd.DataFrame(
            {
                "transaction_id": frame[transaction_id_col].astype(str) if transaction_id_col else "",
                "date": pd.to_datetime(frame[date_col], errors="coerce").dt.date,
                "description": frame[description_col].astype(str).str.strip(),
                "amount": pd.to_numeric(frame[amount_col], errors="coerce"),
                "balance": pd.to_numeric(frame[balance_col], errors="coerce") if balance_col else pd.NA,
                "account_name": frame[account_col].astype(str) if account_col else source_name,
                "source": source_name,
            }
        )
        cleaned = normalized.dropna(subset=["date", "description", "amount"]).reset_index(drop=True)
        cleaned["transaction_id"] = cleaned["transaction_id"].fillna("")
        return cleaned

    def fetch_transactions(self, start_date: date, end_date: date) -> pd.DataFrame:
        if not self.csv_paths:
            raise ValueError("No CSV paths configured")

        frames: list[pd.DataFrame] = []
        for csv_path in self.csv_paths:
            if not csv_path.exists():
                LOGGER.warning("CSV path does not exist: %s", csv_path)
                continue

            LOGGER.info("Loading CSV transactions from %s", csv_path)
            raw = pd.read_csv(csv_path)
            normalized = self._normalize_frame(raw, csv_path.stem)
            filtered = normalized[
                (normalized["date"] >= start_date) & (normalized["date"] <= end_date)
            ].copy()
            frames.append(filtered)

        if not frames:
            return pd.DataFrame(columns=["transaction_id", "date", "description", "amount", "balance", "account_name", "source"])

        return pd.concat(frames, ignore_index=True)
