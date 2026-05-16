from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pandas as pd

from ingestion.csv_ingestor import CSVIngestor


class CSVIngestorTests(unittest.TestCase):
    def test_normalizes_common_alias_columns(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "bank.csv"
            pd.DataFrame(
                {
                    "Posting_Date": ["2026-01-02"],
                    "Merchant": ["Whole Foods"],
                    "Transaction_Amount": [42.12],
                    "Running_Balance": [2500.00],
                    "Account": ["Checking"],
                    "Unique_ID": ["abc-123"],
                }
            ).to_csv(csv_path, index=False)

            ingestor = CSVIngestor([str(csv_path)])
            result = ingestor.fetch_transactions(date(2026, 1, 1), date(2026, 1, 31))

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["description"], "Whole Foods")
        self.assertEqual(result.iloc[0]["transaction_id"], "abc-123")
        self.assertEqual(result.iloc[0]["account_name"], "Checking")


if __name__ == "__main__":
    unittest.main()
