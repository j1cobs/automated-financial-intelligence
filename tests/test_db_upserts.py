from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from database.db import DatabaseClient


def _mock_connect(fetchall_return=None):
    """Build a MagicMock standing in for psycopg.connect(...) that, when used as a
    context manager, yields a connection whose cursor is also a context manager
    (matching the pattern used throughout database/db.py)."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return if fetchall_return is not None else []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False

    connect = MagicMock(return_value=connection)
    return connect, cursor


class UpsertPlaidAccountsTests(unittest.TestCase):
    def test_full_row(self) -> None:
        account = {
            "account_key": "plaid:acc1",
            "account_name": "Checking",
            "owner_name": "Alex",
            "official_name": "Alex Chequing",
            "account_type": "depository",
            "account_subtype": "checking",
            "persistent_account_id": "persist-123",
            "mask": "1234",
            "balance_available": 100.0,
            "balance_current": 200.0,
            "balance_limit": None,
            "iso_currency_code": "CAD",
            "source": "plaid",
        }
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_plaid_accounts([account])

        cursor.executemany.assert_called_once()
        rows = cursor.executemany.call_args[0][1]
        self.assertEqual(
            rows,
            [
                (
                    "plaid:acc1",
                    "Checking",
                    "Alex",
                    "Alex Chequing",
                    "depository",
                    "checking",
                    "persist-123",
                    "1234",
                    100.0,
                    200.0,
                    None,
                    "CAD",
                    "plaid",
                )
            ],
        )

    def test_missing_optionals_are_none(self) -> None:
        account = {
            "account_key": "plaid:acc1",
            "account_name": "Checking",
            "source": "plaid",
        }
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_plaid_accounts([account])

        rows = cursor.executemany.call_args[0][1]
        self.assertEqual(
            rows,
            [("plaid:acc1", "Checking", None, None, None, None, None, None, None, None, None, None, "plaid")],
        )

    def test_empty_list_skips(self) -> None:
        with patch.object(DatabaseClient, "_execute_many") as execute_many:
            DatabaseClient("postgresql://x").upsert_plaid_accounts([])
        execute_many.assert_not_called()


class UpsertTransactionsFieldTests(unittest.TestCase):
    def _row(self, **overrides) -> dict:
        row = {
            "transaction_id": "",
            "date": "2026-07-01",
            "description": "Coffee",
            "amount": 5.0,
            "balance": None,
            "account_key": "plaid:abc123",
            "account_name": "Checking",
            "source": "plaid",
            "category": "uncategorized",
            "outlier_score": 0.0,
            "is_outlier": False,
        }
        row.update(overrides)
        return row

    def test_hash_stable(self) -> None:
        import pandas as pd

        from database.db import build_transaction_hash

        row = self._row()
        frame = pd.DataFrame.from_records([row])
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)

        expected_hash = build_transaction_hash(row)
        first_call_hash = build_transaction_hash(row)
        self.assertEqual(expected_hash, first_call_hash)

    def test_empty_id_to_none(self) -> None:
        import pandas as pd

        frame = pd.DataFrame.from_records([self._row(transaction_id="")])
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)

        rows = cursor.executemany.call_args[0][1]
        self.assertIsNone(rows[0][0])  # external_id

    def test_account_key_fallback(self) -> None:
        import pandas as pd

        row = self._row()
        del row["account_key"]
        del row["account_name"]
        del row["source"]
        frame = pd.DataFrame.from_records([row])
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)

        rows = cursor.executemany.call_args[0][1]
        self.assertEqual(rows[0][2], "unknown:unknown")  # account_key


class LogPipelineRunTests(unittest.TestCase):
    def test_success_row(self) -> None:
        import datetime as dt

        started_at = dt.datetime(2026, 8, 7, 7, 0, 0, tzinfo=dt.timezone.utc)
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").log_pipeline_run(
                started_at,
                "success",
                transactions_inserted=3,
                transactions_updated=1,
                stale_duplicates_removed=2,
            )

        sql, params = cursor.execute.call_args[0]
        self.assertIn("INSERT INTO pipeline_runs", sql)
        self.assertEqual(params, (started_at, "success", 3, 1, 2, None, None))

    def test_failure_row_defaults_counts_to_none(self) -> None:
        import datetime as dt

        started_at = dt.datetime(2026, 8, 7, 7, 0, 0, tzinfo=dt.timezone.utc)
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").log_pipeline_run(
                started_at, "failed", error_class="OperationalError"
            )

        sql, params = cursor.execute.call_args[0]
        self.assertEqual(params, (started_at, "failed", None, None, None, "OperationalError", None))


class CountBySourceTests(unittest.TestCase):
    def test_returns_mapping(self) -> None:
        connect, cursor = _mock_connect([("sample", 1, 10), ("plaid", 3, 500)])
        with patch("database.db.psycopg.connect", connect):
            result = DatabaseClient("postgresql://x").count_by_source()
        self.assertEqual(
            result,
            {
                "sample": {"accounts": 1, "transactions": 10},
                "plaid": {"accounts": 3, "transactions": 500},
            },
        )


class AccountsForSourceTests(unittest.TestCase):
    def test_returns_list(self) -> None:
        connect, cursor = _mock_connect([("sample:Alex Chequing", "Alex Chequing", 10)])
        with patch("database.db.psycopg.connect", connect):
            result = DatabaseClient("postgresql://x").accounts_for_source("sample")
        self.assertEqual(
            result,
            [{"account_key": "sample:Alex Chequing", "account_name": "Alex Chequing", "transaction_count": 10}],
        )
        sql, params = cursor.execute.call_args[0]
        self.assertIn("WHERE a.source = %s", sql)
        self.assertEqual(params, ("sample",))


class PurgeSourceTests(unittest.TestCase):
    def test_deletes_transactions_then_accounts(self) -> None:
        from unittest.mock import PropertyMock

        connect, cursor = _mock_connect()
        type(cursor).rowcount = PropertyMock(side_effect=[10, 1])
        with patch("database.db.psycopg.connect", connect):
            result = DatabaseClient("postgresql://x").purge_source("sample")

        self.assertEqual(result, (10, 1))
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertIn("DELETE FROM transactions", calls[0][0][0])
        self.assertEqual(calls[0][0][1], ("sample",))
        self.assertIn("DELETE FROM accounts", calls[1][0][0])
        self.assertEqual(calls[1][0][1], ("sample",))

    def test_empty_source_raises(self) -> None:
        with self.assertRaises(ValueError):
            DatabaseClient("postgresql://x").purge_source("")


class UpsertCategoriesTests(unittest.TestCase):
    def test_dedup_and_sort(self) -> None:
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_categories(["b", "a", "a"])

        rows = cursor.executemany.call_args[0][1]
        self.assertEqual(rows, [("a",), ("b",)])

    def test_skips_empty(self) -> None:
        with patch.object(DatabaseClient, "_execute_many") as execute_many:
            DatabaseClient("postgresql://x").upsert_categories([])
        execute_many.assert_not_called()


class GetCategoriesTests(unittest.TestCase):
    def test_returns_list(self) -> None:
        connect, cursor = _mock_connect([("Groceries",), ("Transport",)])
        with patch("database.db.psycopg.connect", connect):
            result = DatabaseClient("postgresql://x").get_categories()
        self.assertEqual(result, ["Groceries", "Transport"])


class GetBudgetsTests(unittest.TestCase):
    def test_returns_list(self) -> None:
        connect, cursor = _mock_connect([("Groceries", 400.0), ("Dining", 150.0)])
        with patch("database.db.psycopg.connect", connect):
            result = DatabaseClient("postgresql://x").get_budgets()
        self.assertEqual(
            result,
            [
                {"category": "Groceries", "monthly_limit": 400.0},
                {"category": "Dining", "monthly_limit": 150.0},
            ],
        )


class UpsertBudgetTests(unittest.TestCase):
    def test_calls_execute(self) -> None:
        with patch.object(DatabaseClient, "_execute_many") as execute_many:
            DatabaseClient("postgresql://x").upsert_budget("Groceries", 400.0)

        execute_many.assert_called_once()
        sql, rows = execute_many.call_args[0]
        self.assertIn("INSERT INTO budgets", sql)
        self.assertEqual(rows, [("Groceries", 400.0)])


class UpdateTransactionCategoryTests(unittest.TestCase):
    def test_writes_user_category(self) -> None:
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").update_transaction_category("hash123", "Groceries")

        self.assertEqual(cursor.execute.call_count, 2)
        insert_sql = cursor.execute.call_args_list[0][0][0]
        update_sql = cursor.execute.call_args_list[1][0][0]
        self.assertIn("INSERT INTO categories", insert_sql)
        self.assertIn("SET user_category", update_sql)
        self.assertNotIn("SET category ", update_sql)


class EnsureSchemaTests(unittest.TestCase):
    def test_runs_all_migrations_sorted(self) -> None:
        class _FakeSqlFile:
            def __init__(self, name: str, content: str) -> None:
                self.name = name
                self._content = content

            def __lt__(self, other: _FakeSqlFile) -> bool:
                return self.name < other.name

            def read_text(self, encoding: str = "utf-8") -> str:
                return self._content

        file_b = _FakeSqlFile("002_b.sql", "-- content b")
        file_a = _FakeSqlFile("001_a.sql", "-- content a")

        connect, cursor = _mock_connect()
        with (
            patch("database.db.pathlib.Path.glob", return_value=[file_b, file_a]),
            patch("database.db.psycopg.connect", connect),
        ):
            DatabaseClient("postgresql://x").ensure_schema()

        self.assertEqual(cursor.execute.call_count, 2)
        calls = cursor.execute.call_args_list
        self.assertEqual(calls[0][0][0], "-- content a")
        self.assertEqual(calls[1][0][0], "-- content b")


if __name__ == "__main__":
    unittest.main()
