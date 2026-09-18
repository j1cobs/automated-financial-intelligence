from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from database.db import DatabaseClient


def _mock_connect(fetchall_return=None, fetchone_return=None, rows_affected=None):
    """Build a MagicMock standing in for psycopg.connect(...) that, when used as a
    context manager, yields a connection whose cursor is also a context manager
    (matching the pattern used throughout database/db.py)."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return if fetchall_return is not None else []
    cursor.fetchone.return_value = fetchone_return
    cursor.rowcount = rows_affected if rows_affected is not None else 0
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False

    connect = MagicMock(return_value=connection)
    return connect, cursor


class LinkTransactionTests(unittest.TestCase):
    def test_link_transactions_sets_both_links(self) -> None:
        """Linking two transactions sets linked_transaction_hash on both rows to point
        at each other."""
        # First query returns both rows with no existing links
        connect, cursor = _mock_connect(
            fetchall_return=[
                ("hash_a", None),
                ("hash_b", None),
            ]
        )
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").link_transactions("hash_a", "hash_b")

        # Should execute two UPDATE statements
        execute_calls = cursor.execute.call_args_list
        # First call: SELECT to check existing links
        self.assertIn("SELECT", execute_calls[0][0][0])
        # Second call: UPDATE hash_a to point to hash_b
        self.assertIn("UPDATE", execute_calls[1][0][0])
        self.assertEqual(execute_calls[1][0][1], ("hash_b", "hash_a"))
        # Third call: UPDATE hash_b to point to hash_a
        self.assertIn("UPDATE", execute_calls[2][0][0])
        self.assertEqual(execute_calls[2][0][1], ("hash_a", "hash_b"))

    def test_link_transactions_self_link_raises(self) -> None:
        """Self-link (hash_a == hash_b) raises ValueError."""
        with patch.object(DatabaseClient, "_execute_many"):
            db = DatabaseClient("postgresql://x")
            with self.assertRaises(ValueError) as ctx:
                db.link_transactions("hash_a", "hash_a")
        self.assertIn("Cannot link a transaction to itself", str(ctx.exception))

    def test_link_transactions_already_linked_to_different_raises(self) -> None:
        """Linking a transaction already linked to a DIFFERENT third transaction
        raises ValueError without modifying any row."""
        # First query: hash_a is linked to hash_c (not hash_b)
        connect, cursor = _mock_connect(
            fetchall_return=[
                ("hash_a", "hash_c"),  # hash_a is already linked to hash_c
                ("hash_b", None),
            ]
        )
        with patch("database.db.psycopg.connect", connect):
            db = DatabaseClient("postgresql://x")
            with self.assertRaises(ValueError) as ctx:
                db.link_transactions("hash_a", "hash_b")
        self.assertIn("already linked to", str(ctx.exception))
        # Verify no UPDATE was executed (only the SELECT)
        execute_calls = cursor.execute.call_args_list
        self.assertEqual(len(execute_calls), 1)  # Only the SELECT, no UPDATEs

    def test_link_transactions_already_linked_to_same_is_idempotent(self) -> None:
        """Re-linking an already-linked-to-each-other pair is a no-op success."""
        # Both hash_a and hash_b are already linked to each other
        connect, cursor = _mock_connect(
            fetchall_return=[
                ("hash_a", "hash_b"),
                ("hash_b", "hash_a"),
            ]
        )
        with patch("database.db.psycopg.connect", connect):
            # Should not raise
            DatabaseClient("postgresql://x").link_transactions("hash_a", "hash_b")

        # Still executes UPDATEs (idempotent means no-op behavior, but the method
        # still performs the SQL)
        execute_calls = cursor.execute.call_args_list
        # SELECT + UPDATE + UPDATE
        self.assertEqual(len(execute_calls), 3)

    def test_link_transactions_one_side_already_linked(self) -> None:
        """When one side is already linked to the desired partner, allow it
        (idempotent behavior)."""
        # hash_a is already linked to hash_b, but hash_b has no link yet
        connect, cursor = _mock_connect(
            fetchall_return=[
                ("hash_a", "hash_b"),
                ("hash_b", None),
            ]
        )
        with patch("database.db.psycopg.connect", connect):
            # Should not raise
            DatabaseClient("postgresql://x").link_transactions("hash_a", "hash_b")

        execute_calls = cursor.execute.call_args_list
        # SELECT + UPDATE + UPDATE
        self.assertEqual(len(execute_calls), 3)


class UnlinkTransactionTests(unittest.TestCase):
    def test_unlink_transaction_clears_both_sides(self) -> None:
        """unlink_transaction clears both sides."""
        # First query: transaction_hash is linked to partner
        connect, cursor = _mock_connect(
            fetchone_return=("partner_hash",)
        )
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").unlink_transaction("hash_a")

        execute_calls = cursor.execute.call_args_list
        # First call: SELECT to find the partner
        self.assertIn("SELECT", execute_calls[0][0][0])
        # Second call: UPDATE hash_a to clear its link
        self.assertIn("UPDATE", execute_calls[1][0][0])
        self.assertEqual(execute_calls[1][0][1], ("hash_a",))
        # Third call: UPDATE partner to clear its link
        self.assertIn("UPDATE", execute_calls[2][0][0])
        self.assertEqual(execute_calls[2][0][1], ("partner_hash",))

    def test_unlink_transaction_already_unlinked_is_noop(self) -> None:
        """Calling unlink_transaction on an already-unlinked transaction is a no-op."""
        # First query: transaction_hash has no link (fetchone returns a row with None)
        connect, cursor = _mock_connect(
            fetchone_return=(None,)  # Row with None value
        )
        with patch("database.db.psycopg.connect", connect):
            # Should not raise
            DatabaseClient("postgresql://x").unlink_transaction("hash_a")

        execute_calls = cursor.execute.call_args_list
        # Should have SELECT + UPDATE (the partner UPDATE is skipped since partner is None)
        self.assertEqual(len(execute_calls), 2)  # SELECT + UPDATE
        # The UPDATE should still execute
        self.assertIn("UPDATE", execute_calls[1][0][0])
        self.assertEqual(execute_calls[1][0][1], ("hash_a",))

    def test_unlink_transaction_not_found(self) -> None:
        """Calling unlink_transaction on a non-existent transaction is a no-op."""
        # First query: no row found (fetchone() returns None)
        connect, cursor = _mock_connect(
            fetchone_return=None
        )

        with patch("database.db.psycopg.connect", connect):
            # Should not raise
            DatabaseClient("postgresql://x").unlink_transaction("nonexistent_hash")

        execute_calls = cursor.execute.call_args_list
        # SELECT returns no row, so partner is None and no partner UPDATE runs
        self.assertEqual(len(execute_calls), 2)  # SELECT + UPDATE on hash itself
        self.assertIn("SELECT", execute_calls[0][0][0])
        self.assertIn("UPDATE", execute_calls[1][0][0])


class UpsertTransactionsLinkSurvivalTests(unittest.TestCase):
    def test_linked_transaction_hash_not_in_upsert_sql(self) -> None:
        """Regression check: linked_transaction_hash must NOT appear in the INSERT
        column list or the ON CONFLICT ... DO UPDATE SET list, so a pipeline re-run
        never clears a manual link. This mirrors the invariant for user_category /
        is_recurring / is_duplicate."""
        import pandas as pd

        row = {
            "transaction_id": "plaid-123",
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
        frame = pd.DataFrame.from_records([row])
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)

        sql = cursor.executemany.call_args[0][0]
        # linked_transaction_hash should NOT be in the SQL at all
        self.assertNotIn("linked_transaction_hash", sql)

    def test_all_user_owned_columns_absent_from_upsert(self) -> None:
        """Verify that ALL user-owned columns are absent from the upsert SQL."""
        import pandas as pd

        row = {
            "transaction_id": "plaid-123",
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
        frame = pd.DataFrame.from_records([row])
        connect, cursor = _mock_connect()
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)

        sql = cursor.executemany.call_args[0][0]
        for column in ("user_category", "is_recurring", "is_duplicate", "linked_transaction_hash"):
            self.assertNotIn(column, sql)


if __name__ == "__main__":
    unittest.main()
