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
    resolve_is_recurring,
    upcoming_from_streams,
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


class ResolveIsRecurringTests(unittest.TestCase):
    """The pipeline never overwrites a user decision -- the same rule
    user_category and is_duplicate already follow."""

    def test_user_flag_wins_even_with_no_matching_stream(self):
        self.assertTrue(resolve_is_recurring(True, in_stream=False))

    def test_stream_membership_applies_when_the_user_has_not_decided(self):
        self.assertTrue(resolve_is_recurring(False, in_stream=True))
        self.assertTrue(resolve_is_recurring(None, in_stream=True))

    def test_neither_means_not_recurring(self):
        self.assertFalse(resolve_is_recurring(False, in_stream=False))

    def test_null_flag_is_unknown_not_false(self):
        """NULL means "ingested before this column existed", so it must fall
        through to stream membership rather than being read as a decision."""
        self.assertTrue(resolve_is_recurring(None, in_stream=True))
        self.assertFalse(resolve_is_recurring(None, in_stream=False))


class UpcomingFromStreamsTests(unittest.TestCase):
    def _stream(self, **overrides):
        base = {
            "stream_id": "local:NETFLIX",
            "merchant_key": "NETFLIX",
            "description": "NETFLIX.COM",
            "cadence": CADENCE_MONTHLY,
            "direction": "outflow",
            "last_amount": -16.99,
            "predicted_next_date": date(2026, 9, 20),
            "status": "mature",
            "is_active": True,
        }
        base.update(overrides)
        return base

    def test_one_entry_per_stream(self):
        rows = upcoming_from_streams([self._stream()], today=date(2026, 9, 10))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "NETFLIX.COM")
        self.assertAlmostEqual(rows[0]["amount"], 16.99)

    def test_amount_is_reported_as_a_positive_magnitude(self):
        rows = upcoming_from_streams([self._stream()], today=date(2026, 9, 10))
        self.assertGreater(rows[0]["amount"], 0)

    def test_income_streams_are_excluded(self):
        """Mixing payroll in made the card read as though income were a bill."""
        rows = upcoming_from_streams(
            [self._stream(direction="inflow", last_amount=2500.0)], today=date(2026, 9, 10)
        )
        self.assertEqual(rows, [])

    def test_inactive_streams_are_excluded(self):
        rows = upcoming_from_streams([self._stream(is_active=False)], today=date(2026, 9, 10))
        self.assertEqual(rows, [])

    def test_streams_with_no_prediction_are_skipped_not_blank(self):
        rows = upcoming_from_streams(
            [self._stream(predicted_next_date=None)], today=date(2026, 9, 10)
        )
        self.assertEqual(rows, [])

    def test_a_stale_prediction_rolls_forward_by_whole_cadences(self):
        """A missed or late charge should not leave a date in the past on the card."""
        rows = upcoming_from_streams(
            [self._stream(predicted_next_date=date(2026, 6, 20))], today=date(2026, 9, 10)
        )
        self.assertEqual(rows[0]["next_expected_date"], "2026-09-18")

    def test_sorted_soonest_first(self):
        rows = upcoming_from_streams(
            [
                self._stream(stream_id="a", description="LATER", predicted_next_date=date(2026, 9, 25)),
                self._stream(stream_id="b", description="SOONER", predicted_next_date=date(2026, 9, 12)),
            ],
            today=date(2026, 9, 10),
        )
        self.assertEqual([r["description"] for r in rows], ["SOONER", "LATER"])

    def test_accepts_an_iso_string_date(self):
        """Rows read back from Postgres may arrive as strings."""
        rows = upcoming_from_streams(
            [self._stream(predicted_next_date="2026-09-20")], today=date(2026, 9, 10)
        )
        self.assertEqual(rows[0]["next_expected_date"], "2026-09-20")

    def test_status_is_carried_through_for_confidence_labelling(self):
        rows = upcoming_from_streams(
            [self._stream(status="early_detection")], today=date(2026, 9, 10)
        )
        self.assertEqual(rows[0]["status"], "early_detection")


class StreamRecurringToggleTests(unittest.TestCase):
    """Phase 31's fix for "the same charge can be checked recurring over and
    over": toggling a stream moves every member row at once."""

    def test_membership_uses_the_same_normalizer_as_the_categorizer(self):
        from unittest.mock import MagicMock, patch

        from database.db import DatabaseClient

        cursor = MagicMock()
        # First fetch: the stream's merchant_key. Second: candidate rows.
        cursor.fetchone.return_value = ("NETFLIX.COM",)
        cursor.fetchall.return_value = [
            ("hash-a", None, "NETFLIX.COM"),
            ("hash-b", "NETFLIX.COM", "Purchase / NETFLIX.COM"),
            ("hash-c", None, "SPOTIFY"),
        ]
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False

        with patch("database.db.psycopg.connect", MagicMock(return_value=connection)):
            hashes = DatabaseClient("postgresql://x/y").transaction_hashes_for_stream(
                "local:NETFLIX.COM"
            )

        # hash-b matches via merchant_name even though its raw description differs.
        self.assertEqual(sorted(hashes), ["hash-a", "hash-b"])

    def test_unknown_stream_touches_nothing(self):
        from unittest.mock import MagicMock, patch

        from database.db import DatabaseClient

        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False

        with patch("database.db.psycopg.connect", MagicMock(return_value=connection)):
            client = DatabaseClient("postgresql://x/y")
            self.assertEqual(client.transaction_hashes_for_stream("nope"), [])
            self.assertEqual(client.update_recurring_for_stream("nope", True), 0)


if __name__ == "__main__":
    unittest.main()
