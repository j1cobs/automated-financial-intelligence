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
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import pandas as pd  # noqa: E402

from api import dataload  # noqa: E402

DB_A = "postgresql://localhost/a"
DB_B = "postgresql://localhost/b"


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
        return patch("api.dataload.load_financial_data", return_value=(_tx_df(), _acct_df()))

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

        with patch("api.dataload.load_financial_data", return_value=(_tx_df(), _acct_df())):
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
