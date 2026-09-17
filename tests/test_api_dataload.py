"""Coverage for `api/dataload.py` — PLAN.md Phase 15, Fix 15.

Two of these guard failure modes that produce no error at all, only wrong data:

* **Stale reads after a write.** A category edit returns 204, the frontend refetches, and
  a cache that wasn't invalidated hands back the pre-edit rows. The edit looks like it
  silently failed.
* **In-place mutation of a shared frame.** The cached frames are handed to every request
  in the TTL window. A builder that mutates one instead of copying corrupts every
  subsequent reader, and only for the next 60 seconds — the worst kind of bug to chase.
"""

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import pandas as pd  # noqa: E402

from api import dataload  # noqa: E402

DB_A = "postgresql://localhost/a"
DB_B = "postgresql://localhost/b"


@contextmanager
def _patch_dataload_reads(tx_df: pd.DataFrame | None = None, acct_df: pd.DataFrame | None = None):
    """Patch both reads `load_frames()` performs: `load_financial_data` (the frozen
    Streamlit loader) and `DatabaseClient.get_transaction_pfc_details` (added alongside
    it, without touching the frozen loader -- see api/dataload.py's module docstring).
    Yields the `load_financial_data` mock, since that's what existing tests assert
    call counts against; defaults `get_transaction_pfc_details` to an empty mapping so
    tests that don't care about pfc_detailed/category_source aren't forced to mock it."""
    with patch(
        "api.dataload.load_financial_data",
        return_value=(tx_df if tx_df is not None else _tx_df(), acct_df if acct_df is not None else _acct_df()),
    ) as loader:
        with patch("api.dataload.DatabaseClient") as mock_db_class:
            mock_db_class.return_value.get_transaction_pfc_details.return_value = {}
            yield loader


def _tx_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-05-01"),
                "transaction_hash": "h1",
                "account_key": "k",
                "account_name": "Chequing",
                "owner_name": "Jacob",
                "account_type": "depository",
                "account_subtype": "checking",
                "description": "Thing",
                "amount": 10.0,
                "category": "Shopping",
                "outlier_score": 0.0,
                "is_outlier": False,
                "is_recurring": False,
                "is_duplicate": False,
            }
        ]
    )


def _acct_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "account_key": "k",
                "account_name": "Chequing",
                "official_name": "Jacob Chequing",
                "mask": "0000",
                "owner_name": "Jacob",
                "account_type": "depository",
                "account_subtype": "checking",
                "balance_available": 1.0,
                "balance_current": 1.0,
                "balance_limit": None,
                "manual_credit_limit": None,
                "iso_currency_code": "CAD",
                "updated_at": pd.Timestamp.now(tz="UTC"),
            }
        ]
    )


class DataLoadCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        dataload.clear()

    def tearDown(self) -> None:
        dataload.clear()

    def _patched(self):
        return _patch_dataload_reads()

    def test_second_read_inside_the_window_does_not_hit_the_database(self) -> None:
        with self._patched() as loader:
            dataload.load_frames(DB_A)
            dataload.load_frames(DB_A)
        self.assertEqual(loader.call_count, 1)

    def test_frames_are_enriched_once_and_reused(self) -> None:
        with self._patched():
            first, _ = dataload.load_frames(DB_A)
            second, _ = dataload.load_frames(DB_A)
        # Same object, not merely equal — that is what makes the cache worth having.
        self.assertIs(first, second)
        self.assertIn("tx_type", first.columns)

    def test_invalidate_forces_a_reload(self) -> None:
        with self._patched() as loader:
            dataload.load_frames(DB_A)
            dataload.invalidate(DB_A)
            dataload.load_frames(DB_A)
        self.assertEqual(loader.call_count, 2)

    def test_cache_is_keyed_per_database(self) -> None:
        with self._patched() as loader:
            dataload.load_frames(DB_A)
            dataload.load_frames(DB_B)
        self.assertEqual(loader.call_count, 2)

    def test_invalidating_one_database_leaves_the_other_cached(self) -> None:
        with self._patched() as loader:
            dataload.load_frames(DB_A)
            dataload.load_frames(DB_B)
            dataload.invalidate(DB_A)
            dataload.load_frames(DB_B)
        self.assertEqual(loader.call_count, 2)

    def test_expiry_reloads(self) -> None:
        with self._patched() as loader:
            dataload.load_frames(DB_A)
            with patch(
                "api.dataload.time.monotonic",
                return_value=9_999_999.0,
            ):
                dataload.load_frames(DB_A)
        self.assertEqual(loader.call_count, 2)


class SharedFrameIsNotMutatedTests(unittest.TestCase):
    """`load_frames` documents its result as read-only. This is what makes that true."""

    def setUp(self) -> None:
        dataload.clear()

    def tearDown(self) -> None:
        dataload.clear()

    def test_a_full_builder_pass_leaves_the_cached_frame_untouched(self) -> None:
        from api.filters import DashboardFilters, apply_filters
        from api.viewmodels import (
            build_anomalies,
            build_budget,
            build_cash_flow,
            build_ledger,
            build_net_worth,
            build_overview,
            exclude_duplicate_rows,
        )

        with _patch_dataload_reads():
            tx, acct = dataload.load_frames(DB_A)

        before = tx.copy(deep=True)

        filters = DashboardFilters(period="all_time")
        filtered, all_time = apply_filters(tx, filters)
        real = exclude_duplicate_rows(filtered)
        build_net_worth(acct, tx)
        build_overview(real, acct, exclude_duplicate_rows(all_time))
        build_cash_flow(real)
        build_budget(real, [{"category": "Shopping", "monthly_limit": 100.0}])
        build_anomalies(real)
        build_ledger(filtered)

        # Any builder that mutated in place instead of copying would corrupt every other
        # request served from this same cached frame for the rest of the TTL window.
        pd.testing.assert_frame_equal(tx, before)


class PFCDetailsMergingTests(unittest.TestCase):
    """Test that `load_frames()` merges pfc_detailed and category_source from DB."""

    def setUp(self) -> None:
        dataload.clear()

    def tearDown(self) -> None:
        dataload.clear()

    def test_pfc_details_merged_onto_transaction_frame(self) -> None:
        """When DatabaseClient.get_transaction_pfc_details() returns mappings,
        load_frames() merges them onto the tx_df as pfc_detailed and category_source."""
        from unittest.mock import MagicMock

        tx_df = _tx_df()
        acct_df = _acct_df()

        pfc_details = {
            "h1": ("FOOD_AND_DRINK_RESTAURANTS", "plaid"),
        }

        with patch("api.dataload.load_financial_data", return_value=(tx_df, acct_df)):
            with patch("api.dataload.DatabaseClient") as mock_db_class:
                mock_db = MagicMock()
                mock_db_class.return_value = mock_db
                mock_db.get_transaction_pfc_details.return_value = pfc_details
                prepared, _ = dataload.load_frames(DB_A)

        # The prepared frame should have the merged columns
        self.assertIn("pfc_detailed", prepared.columns)
        self.assertIn("category_source", prepared.columns)
        self.assertEqual(prepared["pfc_detailed"].iloc[0], "FOOD_AND_DRINK_RESTAURANTS")
        self.assertEqual(prepared["category_source"].iloc[0], "plaid")

    def test_missing_hash_gets_none_for_pfc_details(self) -> None:
        """When a transaction_hash is not in the pfc_details mapping,
        pfc_detailed and category_source should be None."""
        from unittest.mock import MagicMock

        tx_df = _tx_df()
        acct_df = _acct_df()

        # Empty mapping: the hash h1 won't be found
        pfc_details = {}

        with patch("api.dataload.load_financial_data", return_value=(tx_df, acct_df)):
            with patch("api.dataload.DatabaseClient") as mock_db_class:
                mock_db = MagicMock()
                mock_db_class.return_value = mock_db
                mock_db.get_transaction_pfc_details.return_value = pfc_details
                prepared, _ = dataload.load_frames(DB_A)

        # The columns exist but the value for this hash is None
        self.assertIn("pfc_detailed", prepared.columns)
        self.assertIn("category_source", prepared.columns)
        self.assertIsNone(prepared["pfc_detailed"].iloc[0])
        self.assertIsNone(prepared["category_source"].iloc[0])

    def test_partial_pfc_details_coverage(self) -> None:
        """When some hashes are in the mapping and others aren't,
        only the mapped ones get values."""
        tx_rows = [
            {
                "date": pd.Timestamp("2026-05-01"),
                "transaction_hash": "h1",
                "account_key": "k",
                "account_name": "Chequing",
                "owner_name": "Jacob",
                "account_type": "depository",
                "account_subtype": "checking",
                "description": "Thing 1",
                "amount": 10.0,
                "category": "Shopping",
                "outlier_score": 0.0,
                "is_outlier": False,
                "is_recurring": False,
                "is_duplicate": False,
            },
            {
                "date": pd.Timestamp("2026-05-02"),
                "transaction_hash": "h2",
                "account_key": "k",
                "account_name": "Chequing",
                "owner_name": "Jacob",
                "account_type": "depository",
                "account_subtype": "checking",
                "description": "Thing 2",
                "amount": 20.0,
                "category": "Shopping",
                "outlier_score": 0.0,
                "is_outlier": False,
                "is_recurring": False,
                "is_duplicate": False,
            },
        ]
        tx_df = pd.DataFrame(tx_rows)
        acct_df = _acct_df()

        # Only h1 is in the mapping
        pfc_details = {"h1": ("FOOD_AND_DRINK", "cascade")}

        with patch("api.dataload.load_financial_data", return_value=(tx_df, acct_df)):
            with patch("api.dataload.DatabaseClient") as mock_db_class:
                mock_db = MagicMock()
                mock_db_class.return_value = mock_db
                mock_db.get_transaction_pfc_details.return_value = pfc_details
                prepared, _ = dataload.load_frames(DB_A)

        # h1 has the value, h2 is None or NaN (pandas converts None in map to NaN)
        h1_row = prepared[prepared["transaction_hash"] == "h1"].iloc[0]
        h2_row = prepared[prepared["transaction_hash"] == "h2"].iloc[0]

        self.assertEqual(h1_row["pfc_detailed"], "FOOD_AND_DRINK")
        self.assertEqual(h1_row["category_source"], "cascade")

        # For h2, the value should be None or NaN -- both are falsy and non-string
        self.assertTrue(pd.isna(h2_row["pfc_detailed"]) or h2_row["pfc_detailed"] is None)
        self.assertTrue(pd.isna(h2_row["category_source"]) or h2_row["category_source"] is None)


class WriteEndpointInvalidationTests(unittest.TestCase):
    """Every write path must drop the cache — see the module docstring."""

    def test_all_write_handlers_invalidate(self) -> None:
        import inspect

        from api.routers import data as data_router

        handlers = [
            data_router.update_credit_limit,
            data_router.update_budget,
            data_router.update_transaction_category,
            data_router.update_transaction_recurring,
            data_router.update_transaction_duplicate,
        ]
        for handler in handlers:
            with self.subTest(handler=handler.__name__):
                source = inspect.getsource(handler)
                self.assertIn(
                    "invalidate_cache",
                    source,
                    f"{handler.__name__} writes to the database without dropping the "
                    "cached frames; its edit would be invisible for up to "
                    f"{dataload.CACHE_TTL_SECONDS}s.",
                )


if __name__ == "__main__":
    unittest.main()
