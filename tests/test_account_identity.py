from __future__ import annotations

import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd

from database.db import DatabaseClient
from scripts.dedupe_accounts import _group_duplicates


def _mock_connect():
    """Same pattern as tests/test_db_upserts.py: a context-manager connection whose
    cursor is also a context manager."""
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False

    connect = MagicMock(return_value=connection)
    return connect, cursor


class MergeAccountTests(unittest.TestCase):
    def test_same_key_is_noop(self) -> None:
        moved, dropped = DatabaseClient("postgresql://x").merge_account("plaid:a", "plaid:a")
        self.assertEqual((moved, dropped), (0, 0))

    def test_drops_collisions_before_reassigning(self) -> None:
        connect, cursor = _mock_connect()
        # Call order: DELETE colliding txns, UPDATE remaining txns, UPDATE manual_credit_limit,
        # DELETE duplicate accounts row. rowcount is read right after the first two.
        type(cursor).rowcount = PropertyMock(side_effect=[9, 1, 0, 0])
        with patch("database.db.psycopg.connect", connect):
            moved, dropped = DatabaseClient("postgresql://x").merge_account("plaid:dup", "plaid:canon")

        self.assertEqual((moved, dropped), (1, 9))
        calls = cursor.execute.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertIn("DELETE FROM transactions d", calls[0][0][0])
        self.assertIn("UPDATE transactions SET account_key", calls[1][0][0])
        self.assertIn("manual_credit_limit", calls[2][0][0])
        self.assertIn("DELETE FROM accounts", calls[3][0][0])
        # The collision DELETE must run before the account_key UPDATE, not after —
        # otherwise the UPDATE raises a unique violation on transactions_natural_key.
        self.assertEqual(calls[0][0][1], ("plaid:dup", "plaid:canon"))
        self.assertEqual(calls[1][0][1], ("plaid:canon", "plaid:dup"))


class CanonicalizeAccountKeysTests(unittest.TestCase):
    def _account(self, **overrides) -> dict:
        row = {
            "account_key": "plaid:new",
            "persistent_account_id": None,
            "official_name": "Chequing Account",
            "account_subtype": "checking",
            "account_type": "depository",
            "owner_name": "Jacob",
            "mask": "9102",
        }
        row.update(overrides)
        return row

    def test_exact_mask_match_wins_over_null_mask_candidate(self) -> None:
        connect, cursor = _mock_connect()
        cursor.fetchone.return_value = None  # no persistent_account_id match
        cursor.fetchall.return_value = [("plaid:masked", "9102"), ("plaid:unmasked", None)]
        with patch("database.db.psycopg.connect", connect):
            remap = DatabaseClient("postgresql://x").canonicalize_account_keys([self._account()])
        self.assertEqual(remap["plaid:new"], "plaid:masked")

    def test_matches_across_differing_owner_name(self) -> None:
        """owner_name records which connection revealed the account, not who owns it, so it
        must not block a match — a joint account seen through a different token must still
        merge onto the existing row."""
        connect, cursor = _mock_connect()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = [("plaid:existing", "4102")]
        with patch("database.db.psycopg.connect", connect):
            remap = DatabaseClient("postgresql://x").canonicalize_account_keys(
                [self._account(mask="4102", owner_name="Alexie")]
            )
        self.assertEqual(remap["plaid:new"], "plaid:existing")
        # owner_name must not appear in the fallback WHERE clause at all.
        fallback_call = cursor.execute.call_args_list[-1]
        self.assertNotIn("owner_name", fallback_call[0][0])

    def test_ambiguous_null_mask_candidates_refuse_to_guess(self) -> None:
        connect, cursor = _mock_connect()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = [("plaid:one", None), ("plaid:two", None)]
        with patch("database.db.psycopg.connect", connect):
            remap = DatabaseClient("postgresql://x").canonicalize_account_keys([self._account(mask=None)])
        # No incoming mask and two equally-valid NULL-mask candidates: stay unmapped rather
        # than guess which one is the same physical account.
        self.assertEqual(remap["plaid:new"], "plaid:new")


class GroupDuplicatesTests(unittest.TestCase):
    def _account(self, key: str, mask: str | None, owner: str, updated: datetime) -> dict:
        return {
            "account_key": key,
            "persistent_account_id": None,
            "official_name": "Chequing Account",
            "account_subtype": "checking",
            "account_type": "depository",
            "owner_name": owner,
            "mask": mask,
            "created_at": updated,
            "updated_at": updated,
        }

    def test_four_row_bucket_partitions_by_mask_ignoring_owner(self) -> None:
        # Masks are populated on all rows here, mirroring the real repair order: migration 008
        # backfills mask from account_name for every row — including the orphans — before
        # dedupe_accounts.py ever groups them.
        accounts = [
            self._account("plaid:9102-orphan", "9102", "Jacob", datetime(2026, 7, 10, 18, 11)),
            self._account("plaid:9102-live", "9102", "Jacob", datetime(2026, 7, 27)),
            self._account("plaid:4102-orphan", "4102", "Jacob", datetime(2026, 7, 10, 18, 11)),
            self._account("plaid:4102-live", "4102", "Jacob", datetime(2026, 7, 27)),
            self._account("plaid:9105-alexie", "9105", "Alexie", datetime(2026, 7, 27)),
        ]
        groups = _group_duplicates(accounts)
        group_key_sets = [{a["account_key"] for a in g} for g in groups]
        self.assertIn({"plaid:9102-orphan", "plaid:9102-live"}, group_key_sets)
        self.assertIn({"plaid:4102-orphan", "plaid:4102-live"}, group_key_sets)
        # The singleton (different mask, different owner) must not be pulled into either group.
        for group in group_key_sets:
            self.assertNotIn("plaid:9105-alexie", group)

    def test_unmasked_rows_left_for_manual_review_when_still_ambiguous(self) -> None:
        # Pre-backfill state (or any future institution that never supplies a mask): unmasked
        # orphans in a bucket with multiple distinct known masks can't be assigned to a specific
        # partition by metadata alone, and must be left out rather than guessed at.
        accounts = [
            self._account("plaid:9102-orphan", None, "Jacob", datetime(2026, 7, 10, 18, 11)),
            self._account("plaid:9102-live", "9102", "Jacob", datetime(2026, 7, 27)),
            self._account("plaid:4102-orphan", None, "Jacob", datetime(2026, 7, 10, 18, 11)),
            self._account("plaid:4102-live", "4102", "Jacob", datetime(2026, 7, 27)),
        ]
        groups = _group_duplicates(accounts)
        grouped_keys = {a["account_key"] for g in groups for a in g}
        self.assertNotIn("plaid:9102-orphan", grouped_keys)
        self.assertNotIn("plaid:4102-orphan", grouped_keys)

    def test_single_known_mask_bucket_groups_together(self) -> None:
        accounts = [
            self._account("plaid:a", None, "Jacob", datetime(2026, 6, 1)),
            self._account("plaid:b", "1234", "Jacob", datetime(2026, 7, 1)),
        ]
        groups = _group_duplicates(accounts)
        self.assertEqual(len(groups), 1)
        self.assertEqual({a["account_key"] for a in groups[0]}, {"plaid:a", "plaid:b"})


class UpsertTransactionsExternalIdTests(unittest.TestCase):
    def _frame(self, records: list[dict]) -> pd.DataFrame:
        base = {
            "date": "2026-07-01",
            "description": "Coffee",
            "amount": 5.0,
            "balance": None,
            "account_key": "plaid:acctA",
            "account_name": "Chequing",
            "source": "plaid",
            "category": "uncategorized",
            "outlier_score": 0.0,
            "is_outlier": False,
        }
        return pd.DataFrame.from_records([{**base, **r} for r in records])

    def _run(self, frame: pd.DataFrame):
        connect, cursor = _mock_connect()
        cursor.fetchall.return_value = []
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)
        return cursor

    def test_insert_is_the_only_statement(self) -> None:
        # No relocation pass: the hash keys on transaction_id, so a revised or re-attributed
        # transaction arrives with an unchanged hash and ON CONFLICT absorbs it.
        cursor = self._run(self._frame([{"transaction_id": "plaid-txn-1"}]))
        sqls = [c[0][0] for c in cursor.executemany.call_args_list]
        self.assertEqual(len(sqls), 1)
        self.assertIn("INSERT INTO transactions", sqls[0])
        self.assertIn("ON CONFLICT (transaction_hash) DO UPDATE", sqls[0])
        self.assertNotIn("DELETE", sqls[0])

    def test_conflict_carries_mutable_attributes(self) -> None:
        # Plaid revises a pending transaction's amount/date/description under a stable
        # transaction_id, and can re-attribute it to another account. Both must update in
        # place rather than insert a twin, so all of these belong in the conflict clause.
        cursor = self._run(self._frame([{"transaction_id": "plaid-txn-1"}]))
        sql = cursor.executemany.call_args_list[-1][0][0]
        for column in ("external_id", "account_key", "transaction_date", "description", "amount"):
            self.assertIn(f"{column} = EXCLUDED.{column}", sql)

    def test_hash_keys_on_transaction_id_not_account(self) -> None:
        # transaction_hash is UNIQUE, so an account-scoped formula would cap the table at one
        # row per (account, date, description, amount) and destroy three of the user's four
        # real IKEA contactless taps. It was tried and reverted for exactly that reason.
        from database.db import build_transaction_hash

        base = {"transaction_id": "plaid-txn-1", "date": "2026-07-01", "description": "Coffee", "amount": 5.0}
        self.assertEqual(
            build_transaction_hash({**base, "account_key": "plaid:acctA"}),
            build_transaction_hash({**base, "account_key": "plaid:acctB"}),
        )

    def test_hash_falls_back_to_account_scope_without_transaction_id(self) -> None:
        from database.db import build_transaction_hash

        base = {"date": "2026-07-01", "description": "Coffee", "amount": 5.0}
        self.assertNotEqual(
            build_transaction_hash({**base, "account_key": "plaid:acctA"}),
            build_transaction_hash({**base, "account_key": "plaid:acctB"}),
        )

    def test_repeated_transactions_each_persist(self) -> None:
        # Four real IKEA taps: same account/date/description/amount, distinct transaction_ids.
        # All four must survive; trimming genuine duplicates is reconcile_transactions' job.
        frame = self._frame([{"transaction_id": f"plaid-txn-{i}"} for i in range(4)])
        cursor = self._run(frame)
        insert_rows = cursor.executemany.call_args_list[-1][0][1]
        self.assertEqual(len(insert_rows), 4)
        self.assertEqual(len({r[1] for r in insert_rows}), 4)  # four distinct hashes

    def test_rows_without_external_id_still_upsert(self) -> None:
        # Seed-data path: no Plaid transaction_id, so identity falls back to the account-scoped
        # transaction_hash. No external_id means no relocation pass at all — exactly one
        # statement — and external_id persists as NULL.
        cursor = self._run(self._frame([{"transaction_id": ""}]))
        sqls = [c[0][0] for c in cursor.executemany.call_args_list]
        self.assertEqual(len(sqls), 1)
        self.assertIn("INSERT INTO transactions", sqls[0])
        self.assertNotIn("DELETE FROM transactions stale", " ".join(sqls))
        insert_rows = cursor.executemany.call_args_list[-1][0][1]
        self.assertIsNone(insert_rows[0][0])


class ReconcileTransactionsTests(unittest.TestCase):
    """reconcile_transactions trims stored copies down to the number Plaid currently
    returns per natural key. These tests pin the two properties that matter most:
    genuinely repeated transactions survive, and history Plaid has dropped is never
    deleted."""

    KEY = ("plaid:acctA", date(2026, 7, 2), "IKEA", 250.00)

    def _frame(self, n: int) -> pd.DataFrame:
        acct, d, desc, amt = self.KEY
        return pd.DataFrame.from_records(
            [
                {
                    "account_key": acct,
                    "date": d,
                    "description": desc,
                    "amount": amt,
                    "transaction_id": f"txn-{i}",
                }
                for i in range(n)
            ]
        )

    def _stored(self, n: int, external_ids: list[str] | None = None, flagged: set[int] | None = None):
        """Stored rows for the shared natural key. `external_ids` defaults to txn-0..txn-n-1,
        i.e. every row is one Plaid currently returns. `flagged` holds indices the user has
        marked as duplicates."""
        acct, d, desc, amt = self.KEY
        ids = external_ids if external_ids is not None else [f"txn-{i}" for i in range(n)]
        flagged = flagged or set()
        # id, account_key, transaction_date, description, amount, created_at, external_id, is_duplicate
        return [
            (
                100 + i,
                acct,
                d,
                desc,
                Decimal("250.00"),
                datetime(2026, 7, 10 + i, 12, 0),
                ids[i],
                i in flagged,
            )
            for i in range(n)
        ]

    def _run(self, fetched_n: int, stored_rows, full_refresh: bool = True):
        connect, cursor = _mock_connect()
        cursor.fetchall.return_value = stored_rows
        with patch("database.db.psycopg.connect", connect):
            deleted = DatabaseClient("postgresql://x").reconcile_transactions(
                self._frame(fetched_n), date(2026, 4, 28), date(2026, 7, 27), full_refresh=full_refresh
            )
        return deleted, cursor

    def test_trims_stale_copy_not_the_current_one(self) -> None:
        # The real case: 5 stored, Plaid returns 4. The extra row carries an external_id Plaid
        # no longer returns, and it is the OLDEST. Deleting by created_at alone would keep the
        # stale row and delete a current one, so the next run re-inserts it and the pipeline
        # thrashes 43-in/43-out forever — which is exactly what happened in production.
        stored = self._stored(5, external_ids=["stale-id", "txn-0", "txn-1", "txn-2", "txn-3"])
        deleted, cursor = self._run(4, stored)
        self.assertEqual(deleted, 1)
        delete_calls = [c for c in cursor.execute.call_args_list if "DELETE" in str(c[0][0])]
        self.assertEqual(len(delete_calls), 1)
        self.assertEqual(delete_calls[0][0][1][0], [100])  # the stale row, despite being oldest

    def test_user_flagged_duplicate_is_deleted_before_its_twin(self) -> None:
        # The user ticked "Duplicate" on the newest, still-current copy. Trimming must remove
        # that row, not its unflagged twin — otherwise the flag silently moves to a row the
        # user never judged, and the copy they rejected survives.
        stored = self._stored(5, flagged={2})
        deleted, cursor = self._run(4, stored)
        self.assertEqual(deleted, 1)
        delete_calls = [c for c in cursor.execute.call_args_list if "DELETE" in str(c[0][0])]
        self.assertEqual(delete_calls[0][0][1][0], [102])  # the flagged row

    def test_among_current_rows_the_earliest_is_kept(self) -> None:
        # All copies are current, so created_at decides and the newest is dropped, preserving
        # user_category / is_recurring / created_at on the survivors.
        deleted, cursor = self._run(4, self._stored(5, external_ids=[f"txn-{i}" for i in range(5)]))
        self.assertEqual(deleted, 1)
        delete_calls = [c for c in cursor.execute.call_args_list if "DELETE" in str(c[0][0])]
        self.assertEqual(delete_calls[0][0][1][0], [104])

    def test_genuinely_repeated_transactions_untouched(self) -> None:
        # Four real IKEA contactless taps, four returned by Plaid: nothing is a duplicate.
        deleted, cursor = self._run(4, self._stored(4))
        self.assertEqual(deleted, 0)
        self.assertFalse([c for c in cursor.execute.call_args_list if "DELETE" in str(c[0][0])])

    def test_key_plaid_no_longer_returns_is_never_deleted(self) -> None:
        # Plaid's window rolls forward and drops old history we legitimately still hold.
        # Absence from the fetch is not evidence of duplication.
        deleted, cursor = self._run(0, self._stored(2))
        self.assertEqual(deleted, 0)
        self.assertFalse([c for c in cursor.execute.call_args_list if "DELETE" in str(c[0][0])])

    def test_float_and_decimal_amounts_bucket_together(self) -> None:
        # Frame carries float 250.0; Postgres returns Decimal("250.00"). If these bucketed
        # separately, reconciliation would see 0 fetched and silently skip.
        deleted, _ = self._run(1, self._stored(3))
        self.assertEqual(deleted, 2)

    def test_full_refresh_false_raises_regardless_of_content(self) -> None:
        # The IKEA-delta hazard, Phase 17: a delta modifying one of four genuine IKEA taps
        # must never reach the trimming logic at all -- the guard fires before any DB read,
        # not based on what the delta or the stored rows actually contain.
        with self.assertRaises(ValueError):
            self._run(1, self._stored(4), full_refresh=False)

    def test_full_refresh_false_raises_even_with_nothing_to_delete(self) -> None:
        # Not "raises when it would have deleted something" -- raises unconditionally.
        with self.assertRaises(ValueError):
            self._run(0, [], full_refresh=False)

    def test_full_refresh_true_with_genuine_full_snapshot_all_four_survive(self) -> None:
        # Pre-Phase-17 behavior is unchanged for an actual full fetch: 4 stored genuine IKEA
        # repeats against a full snapshot containing all 4 rows deletes nothing.
        deleted, cursor = self._run(4, self._stored(4), full_refresh=True)
        self.assertEqual(deleted, 0)
        self.assertFalse([c for c in cursor.execute.call_args_list if "DELETE" in str(c[0][0])])


class DuplicateFlagTests(unittest.TestCase):
    """The user-set is_duplicate flag records a judgement no automatic rule can make: Plaid
    returns genuine repeats (four real IKEA contactless taps) byte-identical to double-posts."""

    def test_update_transaction_duplicate_writes_flag(self) -> None:
        with patch.object(DatabaseClient, "_execute_many") as execute_many:
            DatabaseClient("postgresql://x").update_transaction_duplicate("hash123", True)
        sql, rows = execute_many.call_args[0]
        self.assertIn("UPDATE transactions SET is_duplicate", sql)
        self.assertIn("WHERE transaction_hash = %s", sql)
        self.assertEqual(rows, [(True, "hash123")])

    def test_upsert_never_writes_is_duplicate(self) -> None:
        # A nightly pipeline run must not clear the user's flag. Same protection
        # user_category and is_recurring already rely on: the column is simply never named.
        connect, cursor = _mock_connect()
        cursor.fetchall.return_value = []
        frame = pd.DataFrame.from_records(
            [
                {
                    "transaction_id": "txn-1",
                    "date": "2026-07-01",
                    "description": "Coffee",
                    "amount": 5.0,
                    "balance": None,
                    "account_key": "plaid:acctA",
                    "account_name": "Chequing",
                    "source": "plaid",
                    "category": "uncategorized",
                    "outlier_score": 0.0,
                    "is_outlier": False,
                }
            ]
        )
        with patch("database.db.psycopg.connect", connect):
            DatabaseClient("postgresql://x").upsert_transactions(frame)
        for call in cursor.executemany.call_args_list:
            self.assertNotIn("is_duplicate", call[0][0])


class RehashExternalIdPassTests(unittest.TestCase):
    def test_external_id_duplicates_deleted_keeping_newest(self) -> None:
        connect, cursor = _mock_connect()
        cursor.fetchall.return_value = []
        type(cursor).rowcount = PropertyMock(return_value=60)
        with patch("database.db.psycopg.connect", connect):
            _rehashed, deleted = DatabaseClient("postgresql://x").rehash_transactions()

        first_sql = cursor.execute.call_args_list[0][0][0]
        self.assertIn("DELETE FROM transactions t", first_sql)
        self.assertIn("t.external_id = newer.external_id", first_sql)
        # Newest copy (Plaid's current attribution) survives, matching migration 009.
        self.assertIn("(t.created_at, t.id) < (newer.created_at, newer.id)", first_sql)
        self.assertEqual(deleted, 60)


if __name__ == "__main__":
    unittest.main()
