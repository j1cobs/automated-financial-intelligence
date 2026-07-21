from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from database.db import DatabaseClient, build_transaction_hash


def _make_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame.from_records(rows)


def _mock_connect(existing_hashes: list[str]):
    """Build a MagicMock standing in for psycopg.connect(...) that, when used as a
    context manager, yields a connection whose cursor's fetchall() returns
    existing_hashes (as single-item tuples, matching a real cursor row)."""
    cursor = MagicMock()
    cursor.fetchall.return_value = [(h,) for h in existing_hashes]
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False

    connect = MagicMock(return_value=connection)
    return connect, cursor


class UpsertTransactionsCountTests(unittest.TestCase):
    def _row(self, description: str, amount: float = 10.0) -> dict:
        return {
            "transaction_id": "",
            "date": "2026-07-01",
            "description": description,
            "amount": amount,
            "balance": None,
            "account_key": "plaid:abc123",
            "account_name": "Checking",
            "category": "uncategorized",
            "outlier_score": 0.0,
            "is_outlier": False,
        }

    def test_all_new_when_table_empty(self) -> None:
        frame = _make_frame([self._row("Coffee"), self._row("Tea"), self._row("Lunch")])
        connect, cursor = _mock_connect([])
        with patch("database.db.psycopg.connect", connect):
            inserted, updated = DatabaseClient("postgresql://x").upsert_transactions(frame)
        self.assertEqual((inserted, updated), (3, 0))
        cursor.executemany.assert_called_once()
        self.assertEqual(len(cursor.executemany.call_args[0][1]), 3)

    def test_all_updates_on_rerun(self) -> None:
        rows = [self._row("Coffee"), self._row("Tea")]
        frame = _make_frame(rows)
        hashes = [build_transaction_hash(r) for r in rows]
        connect, cursor = _mock_connect(hashes)
        with patch("database.db.psycopg.connect", connect):
            inserted, updated = DatabaseClient("postgresql://x").upsert_transactions(frame)
        self.assertEqual((inserted, updated), (0, 2))

    def test_mixed_batch(self) -> None:
        rows = [self._row("Coffee"), self._row("Tea"), self._row("Lunch")]
        frame = _make_frame(rows)
        existing = [build_transaction_hash(rows[0])]
        connect, cursor = _mock_connect(existing)
        with patch("database.db.psycopg.connect", connect):
            inserted, updated = DatabaseClient("postgresql://x").upsert_transactions(frame)
        self.assertEqual((inserted, updated), (2, 1))

    def test_intra_batch_duplicate_counted_once(self) -> None:
        duplicate = self._row("Coffee")
        frame = _make_frame([duplicate, dict(duplicate)])
        connect, cursor = _mock_connect([])
        with patch("database.db.psycopg.connect", connect):
            inserted, updated = DatabaseClient("postgresql://x").upsert_transactions(frame)
        self.assertEqual((inserted, updated), (1, 0))
        self.assertEqual(len(cursor.executemany.call_args[0][1]), 1)

    def test_empty_frame_returns_zero_and_skips_db(self) -> None:
        frame = _make_frame([])
        connect, _cursor = _mock_connect([])
        with patch("database.db.psycopg.connect", connect):
            inserted, updated = DatabaseClient("postgresql://x").upsert_transactions(frame)
        self.assertEqual((inserted, updated), (0, 0))
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
