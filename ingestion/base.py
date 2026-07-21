from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class BaseIngestor(ABC):
    """Defines the common ingestion interface."""

    @abstractmethod
    def fetch_transactions(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch transactions and return a normalized DataFrame."""
