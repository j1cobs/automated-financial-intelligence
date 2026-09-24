"""Phase 34: explainable anomaly detection.

Two deterministic detectors replace the unwired Isolation Forest. The
properties these tests protect are the reasons that model was retired:

  - **Explainability.** Every anomaly carries a sentence stating the numbers it
    was derived from, including how much history backs it.
  - **Robustness.** Drift is scored by MAD (median absolute deviation), so one
    unusual month cannot inflate the threshold and mask the next one. A
    standard deviation would.
  - **Silence when nothing is wrong.** The Isolation Forest's fixed
    `contamination=0.03` flagged ~3% of rows no matter what. These emit nothing
    unless a threshold is actually crossed.
  - **No early-month false alarms.** Drift compares spend *to the same day of
    the month* in prior months, never a projection to end-of-month: on day 2 a
    single purchase extrapolates to ~15x and would fire every month.
"""

import unittest
from datetime import date

import pandas as pd

from analytics.anomalies import (
    KIND_CATEGORY_DRIFT,
    KIND_PRICE_CREEP,
    MIN_MONTHS_OF_HISTORY,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    detect_anomalies,
    detect_category_drift,
    detect_price_creep,
    suppress_dismissed,
)


def _rows(month_amounts: dict[str, list[tuple[int, float]]], category="FOOD_AND_DRINK"):
    """month_amounts: {'YYYY-MM': [(day_of_month, amount), ...]} as expenses."""
    out = []
    for month, entries in month_amounts.items():
        year, mon = (int(part) for part in month.split("-"))
        for day, amount in entries:
            out.append(
                {
                    "date": pd.Timestamp(date(year, mon, day)),
                    "month": month,
                    "category": category,
                    "tx_type": "expense",
                    "adjusted_amount": -abs(amount),
                    "description": f"{category} purchase",
                    "merchant_name": None,
                    "transaction_hash": f"h-{month}-{day}-{amount}",
                }
            )
    return pd.DataFrame(out)


def _steady_history(per_month=200.0, months=("2026-05", "2026-06", "2026-07", "2026-08")):
    return {month: [(5, per_month / 2), (9, per_month / 2)] for month in months}


class CategoryDriftTests(unittest.TestCase):
    def test_no_history_means_no_anomaly(self):
        frame = _rows({"2026-09": [(9, 400.0)]})
        self.assertEqual(detect_category_drift(frame, "2026-09", today=date(2026, 9, 9)), [])

    def test_below_the_minimum_history_emits_nothing(self):
        """A median over two months presented as a baseline is a number that
        looks more authoritative than it is."""
        history = _steady_history(months=("2026-07", "2026-08"))
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history)
        self.assertEqual(detect_category_drift(frame, "2026-09", today=date(2026, 9, 9)), [])

    def test_steady_spending_is_not_an_anomaly(self):
        history = _steady_history()
        history["2026-09"] = [(5, 100.0), (9, 100.0)]
        frame = _rows(history)
        self.assertEqual(detect_category_drift(frame, "2026-09", today=date(2026, 9, 9)), [])

    def test_a_clear_overspend_is_flagged(self):
        history = _steady_history()
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history)

        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], KIND_CATEGORY_DRIFT)
        self.assertEqual(found[0]["subject"], "FOOD_AND_DRINK")
        self.assertEqual(found[0]["period"], "2026-09")

    def test_underspending_is_never_flagged(self):
        """This is a budget-drift detector, not a change detector: spending
        less than usual is not something to alert on."""
        history = _steady_history()
        history["2026-09"] = [(5, 1.0), (9, 1.0)]
        frame = _rows(history)
        self.assertEqual(detect_category_drift(frame, "2026-09", today=date(2026, 9, 9)), [])

    def test_compares_against_the_same_day_of_month_not_the_whole_month(self):
        """On day 9, September's $200 is compared against what prior months had
        spent BY day 9 ($200), not against their full-month totals."""
        history = _steady_history(per_month=200.0)
        # Prior months also spend another $600 late in the month.
        for month in list(history):
            history[month] = history[month] + [(25, 600.0)]
        history["2026-09"] = [(5, 100.0), (9, 100.0)]
        frame = _rows(history)

        self.assertEqual(detect_category_drift(frame, "2026-09", today=date(2026, 9, 9)), [])

    def test_no_projection_to_end_of_month(self):
        """Day 2 with one typical purchase must not extrapolate into an alert."""
        history = _steady_history(per_month=200.0)
        history["2026-09"] = [(2, 100.0)]
        frame = _rows(history)

        # By day 2, prior months had spent nothing at all, so a first purchase
        # must not be read as infinite drift.
        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 2))
        self.assertEqual(found, [])

    def test_one_outlier_month_does_not_mask_the_next(self):
        """The MAD argument. With a standard deviation, a single huge month
        inflates the spread enough to hide a genuine overspend afterwards."""
        history = _steady_history(per_month=200.0)
        history["2026-08"] = [(5, 2000.0), (9, 2000.0)]  # one freak month
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history)

        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))
        self.assertEqual(len(found), 1)

    def test_severity_escalates_with_the_statistic(self):
        history = _steady_history(per_month=200.0)
        history["2026-09"] = [(5, 5000.0), (9, 5000.0)]
        frame = _rows(history)

        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))
        self.assertEqual(found[0]["severity"], SEVERITY_HIGH)

    def test_explanation_states_the_numbers_and_the_window(self):
        history = _steady_history(per_month=200.0)
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history)

        explanation = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))[0][
            "explanation"
        ]

        self.assertIn("FOOD_AND_DRINK", explanation)
        self.assertIn("800", explanation.replace(",", ""))
        # How much history backs the claim must be stated, not implied.
        self.assertRegex(explanation, r"\d+ month")

    def test_income_is_ignored(self):
        frame = _rows(_steady_history())
        frame["tx_type"] = "income"
        self.assertEqual(detect_category_drift(frame, "2026-09", today=date(2026, 9, 9)), [])

    def test_contributing_hashes_are_reported_for_the_streamlit_shim(self):
        history = _steady_history()
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history)

        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))
        self.assertTrue(found[0]["contributing_hashes"])


class PriceCreepTests(unittest.TestCase):
    def _stream(self, **overrides):
        base = {
            "stream_id": "local:NETFLIX",
            "merchant_key": "NETFLIX.COM",
            "description": "NETFLIX.COM",
            "direction": "outflow",
            "last_amount": -22.99,
        }
        base.update(overrides)
        return base

    def _history(self, amounts):
        return pd.DataFrame(
            [
                {
                    "date": pd.Timestamp(date(2026, 5 + index, 5)),
                    "description": "NETFLIX.COM",
                    "merchant_name": None,
                    "adjusted_amount": -abs(amount),
                    "transaction_hash": f"h{index}",
                }
                for index, amount in enumerate(amounts)
            ]
        )

    def test_a_stable_price_is_not_an_anomaly(self):
        frame = self._history([16.99, 16.99, 16.99])
        streams = [self._stream(last_amount=-16.99)]
        self.assertEqual(detect_price_creep(frame, streams, "2026-07"), [])

    def test_a_real_increase_is_flagged(self):
        frame = self._history([16.99, 16.99, 22.99])
        found = detect_price_creep(frame, [self._stream()], "2026-07")

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["kind"], KIND_PRICE_CREEP)
        self.assertEqual(found[0]["subject"], "local:NETFLIX")
        self.assertIn("16.99", found[0]["explanation"])
        self.assertIn("22.99", found[0]["explanation"])

    def test_a_price_decrease_is_not_flagged(self):
        frame = self._history([22.99, 22.99, 16.99])
        streams = [self._stream(last_amount=-16.99)]
        self.assertEqual(detect_price_creep(frame, streams, "2026-07"), [])

    def test_dual_threshold_suppresses_noise_on_small_streams(self):
        """A 20% rise on a $2 charge is 40 cents -- percentage alone would
        flag it, which is why the dollar floor exists."""
        frame = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp(date(2026, 7, 5)),
                    "description": "SMALL",
                    "merchant_name": None,
                    "adjusted_amount": -2.00,
                    "transaction_hash": "s1",
                },
                {
                    "date": pd.Timestamp(date(2026, 8, 5)),
                    "description": "SMALL",
                    "merchant_name": None,
                    "adjusted_amount": -2.40,
                    "transaction_hash": "s2",
                },
            ]
        )
        streams = [self._stream(merchant_key="SMALL", description="SMALL", last_amount=-2.40)]
        self.assertEqual(detect_price_creep(frame, streams, "2026-07"), [])

    def test_dual_threshold_suppresses_a_large_but_trivial_percentage(self):
        """$4 on a $400 charge is 1% -- the dollar amount alone would flag it."""
        frame = self._history([400.0, 400.0, 404.0])
        streams = [self._stream(last_amount=-404.0)]
        self.assertEqual(detect_price_creep(frame, streams, "2026-07"), [])

    def test_severity_escalates_on_a_big_jump(self):
        frame = self._history([16.99, 16.99, 49.99])
        found = detect_price_creep(frame, [self._stream(last_amount=-49.99)], "2026-07")
        self.assertEqual(found[0]["severity"], SEVERITY_HIGH)

    def test_a_single_occurrence_has_nothing_to_compare_against(self):
        frame = self._history([22.99])
        self.assertEqual(detect_price_creep(frame, [self._stream()], "2026-05"), [])

    def test_income_streams_are_ignored(self):
        frame = self._history([16.99, 16.99, 22.99])
        streams = [self._stream(direction="inflow")]
        self.assertEqual(detect_price_creep(frame, streams, "2026-07"), [])

    def test_a_rise_in_an_earlier_month_does_not_re_fire(self):
        """The bug this scoping exists for: without it, the latest occurrence is
        whenever it happened, compared against everything before it, and then
        stamped with the CURRENT month -- so a price rise six months ago
        produces a fresh, undismissed anomaly every month thereafter."""
        frame = self._history([16.99, 16.99, 22.99])  # rise landed in July
        self.assertEqual(detect_price_creep(frame, [self._stream()], "2026-08"), [])
        self.assertEqual(detect_price_creep(frame, [self._stream()], "2026-09"), [])

    def test_the_period_it_is_stamped_with_is_the_one_it_happened_in(self):
        found = detect_price_creep(self._history([16.99, 16.99, 22.99]), [self._stream()], "2026-07")
        self.assertEqual(found[0]["period"], "2026-07")


class SuppressionTests(unittest.TestCase):
    def _anomaly(self, period="2026-09"):
        return {
            "kind": KIND_CATEGORY_DRIFT,
            "subject": "FOOD_AND_DRINK",
            "period": period,
            "severity": SEVERITY_MEDIUM,
            "explanation": "…",
        }

    def test_a_dismissal_hides_that_period(self):
        dismissed = [{"kind": KIND_CATEGORY_DRIFT, "subject": "FOOD_AND_DRINK", "period": "2026-09"}]
        self.assertEqual(suppress_dismissed([self._anomaly()], dismissed), [])

    def test_a_dismissal_does_not_silence_the_next_period(self):
        """The point of period-scoped dismissal: dismissing September's Dining
        drift because of a birthday must not hide October's."""
        dismissed = [{"kind": KIND_CATEGORY_DRIFT, "subject": "FOOD_AND_DRINK", "period": "2026-09"}]
        october = self._anomaly(period="2026-10")
        self.assertEqual(suppress_dismissed([october], dismissed), [october])

    def test_a_dismissal_of_one_subject_does_not_hide_another(self):
        dismissed = [{"kind": KIND_CATEGORY_DRIFT, "subject": "TRAVEL", "period": "2026-09"}]
        self.assertEqual(len(suppress_dismissed([self._anomaly()], dismissed)), 1)

    def test_no_dismissals_changes_nothing(self):
        self.assertEqual(len(suppress_dismissed([self._anomaly()], [])), 1)


class DetectAnomaliesTests(unittest.TestCase):
    def test_runs_both_detectors_and_is_stable_across_runs(self):
        history = _steady_history()
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history)

        first = detect_anomalies(frame, [], "2026-09", today=date(2026, 9, 9))
        second = detect_anomalies(frame, [], "2026-09", today=date(2026, 9, 9))

        # UNIQUE(kind, subject, period) makes persistence idempotent, so
        # detection must be deterministic for that to mean anything.
        self.assertEqual(
            [(a["kind"], a["subject"], a["period"]) for a in first],
            [(a["kind"], a["subject"], a["period"]) for a in second],
        )

    def test_every_anomaly_carries_the_persisted_shape(self):
        history = _steady_history()
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        found = detect_anomalies(_rows(history), [], "2026-09", today=date(2026, 9, 9))

        for anomaly in found:
            self.assertEqual(
                set(anomaly),
                {"kind", "subject", "period", "severity", "explanation", "contributing_hashes"},
            )

    def test_minimum_history_constant_is_what_the_tests_assume(self):
        self.assertEqual(MIN_MONTHS_OF_HISTORY, 3)


if __name__ == "__main__":
    unittest.main()


class ContributingHashesTests(unittest.TestCase):
    """The `is_outlier` shim can only flag rows if the frame carries hashes.

    `PlaidIngestor._normalize` does NOT produce `transaction_hash` -- it is
    computed inside `upsert_transactions` and never written back. Feeding the
    ingested frame here therefore yielded no hashes, and `set_outlier_flags([])`
    cleared every flag without setting any: the shim guaranteed exactly the
    empty Streamlit view it exists to prevent.
    """

    def test_no_hashes_when_the_column_is_absent(self):
        history = _steady_history()
        history["2026-09"] = [(5, 400.0), (9, 400.0)]
        frame = _rows(history).drop(columns=["transaction_hash"])

        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))
        self.assertEqual(found[0]["contributing_hashes"], [])

    def test_hashes_are_the_largest_contributors(self):
        history = _steady_history()
        history["2026-09"] = [(5, 50.0), (7, 700.0), (9, 60.0)]
        frame = _rows(history)

        found = detect_category_drift(frame, "2026-09", today=date(2026, 9, 9))
        hashes = found[0]["contributing_hashes"]

        self.assertLessEqual(len(hashes), 3)
        # The $700 row must be in there; it is what drove the anomaly.
        self.assertIn("h-2026-09-7-700.0", hashes)
