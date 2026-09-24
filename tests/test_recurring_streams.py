"""Phase 30: recurring charges as detected streams.

`derive_streams` is the fallback for when Plaid's recurring add-on is not
entitled. It must produce rows of exactly the same shape the Plaid path does,
so everything downstream is indifferent to which produced them.
"""

import unittest
from datetime import date

import pandas as pd

from analytics.recurring import (
    CADENCE_ANNUALLY,
    CADENCE_BIWEEKLY,
    CADENCE_MONTHLY,
    CADENCE_UNKNOWN,
    CADENCE_WEEKLY,
    cadence_from_days,
    derive_streams,
    predict_next_date,
)


def _frame(rows):
    return pd.DataFrame(rows)


def _tx(description, dates, amount=-16.99, category="ENTERTAINMENT", merchant=None):
    return [
        {
            "date": pd.Timestamp(d),
            "description": description,
            "merchant_name": merchant,
            "amount": amount,
            "category": category,
        }
        for d in dates
    ]


class CadenceFromDaysTests(unittest.TestCase):
    def test_recognises_the_common_cadences(self):
        self.assertEqual(cadence_from_days(7), CADENCE_WEEKLY)
        self.assertEqual(cadence_from_days(14), CADENCE_BIWEEKLY)
        self.assertEqual(cadence_from_days(30), CADENCE_MONTHLY)
        self.assertEqual(cadence_from_days(365), CADENCE_ANNUALLY)

    def test_tolerates_real_world_drift(self):
        """Billing dates wobble: 28-31 days is still monthly."""
        for days in (28, 29, 31, 33):
            self.assertEqual(cadence_from_days(days), CADENCE_MONTHLY)

    def test_unrecognised_gaps_are_unknown_not_guessed(self):
        self.assertEqual(cadence_from_days(3), CADENCE_UNKNOWN)
        self.assertEqual(cadence_from_days(120), CADENCE_UNKNOWN)

    def test_non_positive_is_unknown(self):
        self.assertEqual(cadence_from_days(0), CADENCE_UNKNOWN)
        self.assertEqual(cadence_from_days(-7), CADENCE_UNKNOWN)


class PredictNextDateTests(unittest.TestCase):
    def test_adds_the_median_gap(self):
        self.assertEqual(predict_next_date(date(2026, 9, 1), 30), date(2026, 10, 1))

    def test_returns_none_without_a_usable_gap(self):
        self.assertIsNone(predict_next_date(date(2026, 9, 1), 0))
        self.assertIsNone(predict_next_date(None, 30))


class DeriveStreamsTests(unittest.TestCase):
    def test_empty_frame_yields_no_streams(self):
        self.assertEqual(derive_streams(_frame([])), [])

    def test_detects_a_monthly_subscription(self):
        rows = _tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"])
        streams = derive_streams(_frame(rows))

        self.assertEqual(len(streams), 1)
        stream = streams[0]
        self.assertEqual(stream["cadence"], CADENCE_MONTHLY)
        self.assertEqual(stream["direction"], "outflow")
        self.assertEqual(stream["source"], "local")
        self.assertTrue(stream["stream_id"].startswith("local:"))
        self.assertEqual(stream["status"], "mature")

    def test_two_occurrences_are_early_detection_not_mature(self):
        """Plaid calls a stream mature at 3+ occurrences; match that, so the UI
        can mark a nascent stream as lower confidence rather than asserting it."""
        rows = _tx("NETFLIX.COM", ["2026-07-05", "2026-08-05"])
        streams = derive_streams(_frame(rows))

        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["status"], "early_detection")

    def test_a_single_occurrence_is_not_a_stream(self):
        """One charge has no cadence to infer; inventing one would produce a
        stream that cannot predict anything."""
        rows = _tx("NETFLIX.COM", ["2026-08-05"])
        self.assertEqual(derive_streams(_frame(rows)), [])

    def test_predicts_the_next_date_from_the_last_occurrence(self):
        rows = _tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"])
        stream = derive_streams(_frame(rows))[0]

        self.assertEqual(stream["last_date"], date(2026, 8, 5))
        self.assertEqual(stream["predicted_next_date"], date(2026, 9, 4))

    def test_income_is_an_inflow(self):
        rows = _tx("PAYROLL", ["2026-06-15", "2026-07-15", "2026-08-15"], amount=2500.0)
        stream = derive_streams(_frame(rows))[0]
        self.assertEqual(stream["direction"], "inflow")

    def test_last_amount_is_the_most_recent_not_the_largest(self):
        rows = _tx("NETFLIX.COM", ["2026-06-05"], amount=-16.99)
        rows += _tx("NETFLIX.COM", ["2026-07-05"], amount=-16.99)
        rows += _tx("NETFLIX.COM", ["2026-08-05"], amount=-22.99)
        stream = derive_streams(_frame(rows))[0]
        self.assertAlmostEqual(float(stream["last_amount"]), -22.99)

    def test_separate_merchants_are_separate_streams(self):
        rows = _tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"])
        rows += _tx("SPOTIFY", ["2026-06-10", "2026-07-10", "2026-08-10"], amount=-10.99)
        streams = derive_streams(_frame(rows))
        self.assertEqual(len(streams), 2)

    def test_irregular_spending_is_not_a_stream(self):
        """Three trips to the same shop at random intervals is not a subscription."""
        rows = _tx("CORNER STORE", ["2026-06-01", "2026-06-04", "2026-08-19"], amount=-12.0)
        streams = derive_streams(_frame(rows))
        self.assertEqual(streams, [])

    def test_stream_ids_are_stable_across_runs(self):
        """Upserts are keyed on stream_id, so an unstable id would duplicate the
        stream on every pipeline run."""
        rows = _tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"])
        first = derive_streams(_frame(rows))[0]["stream_id"]
        second = derive_streams(_frame(rows))[0]["stream_id"]
        self.assertEqual(first, second)

    def test_every_row_has_the_plaid_path_shape(self):
        rows = _tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"])
        stream = derive_streams(_frame(rows))[0]
        self.assertEqual(
            set(stream),
            {
                "stream_id",
                "merchant_key",
                "description",
                "category",
                "cadence",
                "direction",
                "last_amount",
                "last_date",
                "predicted_next_date",
                "status",
                "source",
                "is_active",
            },
        )



class RecurringStreamDbTests(unittest.TestCase):
    """Persistence is keyed on stream_id, so re-detection must update in place."""

    def test_upsert_updates_in_place_on_conflict(self):
        from unittest.mock import patch

        from database.db import DatabaseClient

        client = DatabaseClient("postgresql://x/y")
        stream = derive_streams(
            _frame(_tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"]))
        )[0]

        with patch.object(client, "_execute_many") as execute_many:
            written = client.upsert_recurring_streams([stream])

        self.assertEqual(written, 1)
        sql, params = execute_many.call_args[0]
        self.assertIn("ON CONFLICT (stream_id) DO UPDATE", sql)
        self.assertEqual(params[0][0], stream["stream_id"])

    def test_upsert_of_nothing_writes_nothing(self):
        from unittest.mock import patch

        from database.db import DatabaseClient

        client = DatabaseClient("postgresql://x/y")
        with patch.object(client, "_execute_many") as execute_many:
            self.assertEqual(client.upsert_recurring_streams([]), 0)
        execute_many.assert_not_called()

    def test_rerunning_detection_yields_the_same_primary_key(self):
        """The whole reason stream_id must be derived, not generated: an
        unstable id would add a duplicate stream on every pipeline run."""
        rows = _frame(_tx("NETFLIX.COM", ["2026-06-05", "2026-07-05", "2026-08-05"]))
        self.assertEqual(
            [s["stream_id"] for s in derive_streams(rows)],
            [s["stream_id"] for s in derive_streams(rows)],
        )


class MigrationTests(unittest.TestCase):
    def test_migration_is_re_runnable(self):
        from pathlib import Path

        sql = (
            Path(__file__).resolve().parent.parent
            / "database"
            / "migrations"
            / "027_recurring_streams.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS recurring_streams", sql)
        self.assertIn("stream_id            TEXT PRIMARY KEY", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS", sql)


if __name__ == "__main__":
    unittest.main()
