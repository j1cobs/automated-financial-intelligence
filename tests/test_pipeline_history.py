"""`pipeline.runner._load_enriched_history`, run against an actual Postgres.

`tests/test_pipeline_runner.py::LoadEnrichedHistoryDtypeTests` mocks
`load_financial_data` and *assumes* the driver hands `date` back as object dtype
(`datetime.date`). That assumption is what the `pd.to_datetime` fix in
`_load_enriched_history` rests on, and a mock cannot notice if psycopg ever stops
behaving that way. Without the conversion, `enrich_transactions` raised on `.dt`
and stream detection silently produced zero rows in production.

These tests read real rows through the real query, so the assumption is checked
rather than asserted, and the whole path runs through to `derive_streams`.
Skipped unless `MIGRATION_TEST_DATABASE_URL` is set.
"""

from __future__ import annotations

import datetime as dt
import unittest

import pandas as pd

from analytics.recurring import derive_streams
from database.frames import load_financial_data
from pipeline.runner import _load_enriched_history
from tests.pg_support import PostgresBackedTestCase


class LoadEnrichedHistoryAgainstPostgresTests(PostgresBackedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed_account()

    def _seed_three(self) -> None:
        self.seed_transaction("h-1", "2026-07-03", "COFFEE SHOP", -4.50)
        self.seed_transaction("h-2", "2026-07-10", "BOOKSTORE", -21.00)
        self.seed_transaction("h-3", "2026-07-17", "PAYROLL", 1800.00)

    def test_the_driver_returns_object_dtype_for_transaction_date(self):
        """Pins the fact the fix in `_load_enriched_history` depends on, and the
        fact the mocked test in test_pipeline_runner.py assumes: psycopg returns
        `datetime.date` for a DATE column, so the frame's `date` is object dtype."""
        self.seed_transaction("h-1", "2026-07-03", "COFFEE SHOP", -4.50)

        tx_df, _accounts = load_financial_data(self.url)

        self.assertEqual(tx_df["date"].dtype, object)
        first = tx_df["date"].iloc[0]
        self.assertIsInstance(first, dt.date)
        self.assertNotIsInstance(first, dt.datetime)
        self.assertNotIsInstance(first, pd.Timestamp)

    def test_history_loads_and_enriches_from_real_rows(self):
        self._seed_three()

        history = _load_enriched_history(self.client())

        self.assertEqual(len(history), 3)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(history["date"]))
        self.assertIn("month", history.columns)
        self.assertEqual(set(history["month"].astype(str)), {"2026-07"})

    def test_duplicate_flagged_rows_are_excluded(self):
        self._seed_three()
        self.execute(
            "UPDATE transactions SET is_duplicate = TRUE WHERE transaction_hash = %s",
            ("h-2",),
        )

        history = _load_enriched_history(self.client())

        self.assertEqual(len(history), 2)
        self.assertNotIn("h-2", set(history["transaction_hash"]))

    def test_real_rows_flow_through_into_stream_detection(self):
        """The path that was dead in production: stream detection found nothing
        because the history frame could not even be built."""
        for month in ("05", "06", "07", "08"):
            self.seed_transaction(
                f"h-nflx-{month}",
                f"2026-{month}-02",
                "NETFLIX.COM",
                -16.99,
                merchant_name="NETFLIX.COM",
            )
        self.seed_transaction("h-grocer", "2026-08-05", "SOME GROCER", -52.10)

        history = _load_enriched_history(self.client())
        streams = derive_streams(history)

        self.assertEqual(len(streams), 1)
        stream = streams[0]
        self.assertEqual(stream["cadence"], "MONTHLY")
        self.assertEqual(stream["direction"], "outflow")
        self.assertEqual(stream["status"], "mature")
        self.assertIn("netflix", stream["merchant_key"].lower())


if __name__ == "__main__":
    unittest.main()
