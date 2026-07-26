from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from scripts.seed_sample_data import ACCOUNTS, generate, main

REQUIRED_COLUMNS = {
    "date",
    "description",
    "amount",
    "balance",
    "account_name",
    "source",
    "transaction_id",
    "category",
    "outlier_score",
    "is_outlier",
}

# Canonical Phase 3c seed categories (title case), as used by generate().
CANONICAL_CATEGORIES = {
    "Income",
    "Housing",
    "Utilities",
    "Subscriptions",
    "Transport",
    "Transfer",
    "Groceries",
    "ATM",
    "Dining",
    "Shopping",
    "Travel",
}


class GenerateTests(unittest.TestCase):
    def test_generate_produces_rows(self) -> None:
        _, frame = generate(120)
        self.assertGreater(len(frame), 100)
        self.assertTrue(REQUIRED_COLUMNS.issubset(set(frame.columns)))

    def test_generate_both_owners_present(self) -> None:
        accounts, _ = generate(120)
        self.assertEqual(len(accounts), len(ACCOUNTS))
        owner_names = {a["owner_name"] for a in accounts}
        self.assertIn("Alex", owner_names)
        self.assertIn("Sam", owner_names)

    def test_generate_anomalies_flagged(self) -> None:
        _, frame = generate(120)
        outliers = frame[frame["is_outlier"]]
        self.assertEqual(len(outliers), 3)
        self.assertTrue((outliers["outlier_score"] == 0.9).all())

    def test_generate_categories_canonical(self) -> None:
        _, frame = generate(120)
        categories = set(frame["category"].unique())
        self.assertTrue(categories.issubset(CANONICAL_CATEGORIES))

    def test_generate_transfer_pair(self) -> None:
        _, frame = generate(120)
        transfer_rows = frame[frame["description"].isin(["Payment - Thank You", "Credit Card Payment"])]
        self.assertTrue((transfer_rows["category"] == "Transfer").all())
        amounts = set(transfer_rows["amount"].unique())
        self.assertIn(-350.0, amounts)
        self.assertIn(350.0, amounts)

    def test_generate_source_is_sample(self) -> None:
        _, frame = generate(120)
        self.assertTrue((frame["source"] == "sample").all())

    def test_generate_deterministic(self) -> None:
        _, frame1 = generate(120)
        _, frame2 = generate(120)
        pd.testing.assert_frame_equal(frame1, frame2)


class MainTests(unittest.TestCase):
    def test_main_calls_db_in_order(self) -> None:
        db_instance = MagicMock()
        db_instance.upsert_transactions.return_value = (1, 0)
        with (
            patch("scripts.seed_sample_data.load_settings") as load_settings,
            patch("scripts.seed_sample_data.DatabaseClient", return_value=db_instance),
            patch("sys.argv", ["seed_sample_data.py"]),
        ):
            load_settings.return_value = MagicMock(database_url="postgresql://x")
            main()

        db_instance.ensure_schema.assert_called_once()
        db_instance.upsert_plaid_accounts.assert_called_once()
        db_instance.upsert_categories.assert_called_once()
        db_instance.upsert_transactions.assert_called_once()

        manager = db_instance.mock_calls
        call_names = [c[0] for c in manager]
        expected_order = [
            "ensure_schema",
            "upsert_plaid_accounts",
            "upsert_categories",
            "upsert_transactions",
        ]
        filtered = [name for name in call_names if name in expected_order]
        self.assertEqual(filtered, expected_order)


if __name__ == "__main__":
    unittest.main()
