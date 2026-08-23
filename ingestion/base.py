from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import NamedTuple

import pandas as pd


class IngestResult(NamedTuple):
    transactions: pd.DataFrame
    duplicate_accounts_skipped: int


class BaseIngestor(ABC):
    """Defines the common ingestion interface."""

    @abstractmethod
    def fetch_transactions(self, start_date: date, end_date: date) -> IngestResult:
        """Fetch transactions and return a normalized DataFrame plus a count of accounts
        skipped as duplicates (e.g. the same real account exposed through two connections)."""
