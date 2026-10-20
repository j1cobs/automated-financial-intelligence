"""Phase 33: generic savings goals.

Nothing here knows what a house is. A down payment, a car and an emergency fund
are the same shape; the goal that prompted this feature is just one instance.

The property these tests exist to protect is that **a pace is never surfaced
without its basis**. `account_balance_snapshots` only began collecting around
2026-08-25, so balance-derived pace has thin history today and the honest answer
is a cash-flow figure that says so — not a confident-looking number built on
four weeks.
"""

import unittest
from datetime import date

from analytics.goals import (
    BALANCE_BASIS_MIN_WEEKS,
    BASIS_BALANCE,
    BASIS_CASHFLOW,
    contested_amounts,
    pace,
    progress,
    projection,
    what_if,
)


def _goal(**overrides):
    base = {
        "id": 1,
        "name": "Down payment",
        "target_amount": 80000.0,
        "target_date": date(2027, 6, 1),
        "baseline_amount": 12000.0,
        "started_on": date(2026, 6, 1),
        "account_keys": ["plaid:savings", "plaid:tfsa"],
    }
    base.update(overrides)
    return base


def _balances(**by_key):
    return dict(by_key)


class ProgressTests(unittest.TestCase):
    def test_progress_excludes_the_baseline(self):
        """Progress measures growth since the goal started, not money that was
        already sitting there when it was created."""
        saved = progress(_goal(), {"plaid:savings": 20000.0, "plaid:tfsa": 14200.0})
        self.assertAlmostEqual(saved, 22200.0)

    def test_only_linked_accounts_count(self):
        saved = progress(_goal(), {"plaid:savings": 20000.0, "plaid:tfsa": 14200.0, "plaid:chequing": 9999.0})
        self.assertAlmostEqual(saved, 22200.0)

    def test_a_missing_account_contributes_nothing_rather_than_erroring(self):
        saved = progress(_goal(), {"plaid:savings": 20000.0})
        self.assertAlmostEqual(saved, 8000.0)

    def test_progress_can_be_negative_if_the_balance_fell_below_baseline(self):
        """Reporting a floor of zero would hide that the user spent the money."""
        saved = progress(_goal(), {"plaid:savings": 5000.0, "plaid:tfsa": 1000.0})
        self.assertAlmostEqual(saved, -6000.0)

    def test_a_goal_with_no_linked_accounts_has_no_progress(self):
        self.assertAlmostEqual(progress(_goal(account_keys=[]), {"plaid:savings": 5.0}), -12000.0)


class PaceTests(unittest.TestCase):
    def _snapshots(self, weeks: int, weekly_growth: float = 500.0):
        """One snapshot per week, growing steadily."""
        rows = []
        for index in range(weeks + 1):
            rows.append(
                {
                    "snapshot_date": date(2026, 6, 1) + __import__("datetime").timedelta(weeks=index),
                    "balance": 12000.0 + weekly_growth * index,
                }
            )
        return rows

    def test_below_the_threshold_falls_back_to_cash_flow(self):
        amount, basis, weeks = pace(_goal(), self._snapshots(4), cashflow_monthly=2150.0)

        self.assertEqual(basis, BASIS_CASHFLOW)
        self.assertAlmostEqual(amount, 2150.0)
        self.assertEqual(weeks, 4)

    def test_at_the_threshold_switches_to_balance(self):
        amount, basis, weeks = pace(
            _goal(), self._snapshots(BALANCE_BASIS_MIN_WEEKS), cashflow_monthly=2150.0
        )

        self.assertEqual(basis, BASIS_BALANCE)
        self.assertGreater(amount, 0)
        self.assertEqual(weeks, BALANCE_BASIS_MIN_WEEKS)

    def test_the_switch_is_hard_not_blended(self):
        """One number with one stated provenance. A weighted blend would give a
        figure nobody can reconstruct by looking at it."""
        below = pace(_goal(), self._snapshots(BALANCE_BASIS_MIN_WEEKS - 1), cashflow_monthly=2150.0)
        at = pace(_goal(), self._snapshots(BALANCE_BASIS_MIN_WEEKS), cashflow_monthly=2150.0)

        self.assertEqual(below[1], BASIS_CASHFLOW)
        self.assertAlmostEqual(below[0], 2150.0)
        self.assertEqual(at[1], BASIS_BALANCE)

    def test_balance_pace_is_monthly_growth(self):
        # 12 weeks at $500/week = $6000 over ~2.76 months -> ~$2173/month.
        amount, basis, _weeks = pace(_goal(), self._snapshots(12), cashflow_monthly=0.0)
        self.assertEqual(basis, BASIS_BALANCE)
        self.assertAlmostEqual(amount, 6000.0 / (12 * 7 / 30.44), places=0)

    def test_no_snapshots_still_returns_a_basis(self):
        amount, basis, weeks = pace(_goal(), [], cashflow_monthly=2150.0)
        self.assertEqual(basis, BASIS_CASHFLOW)
        self.assertEqual(weeks, 0)
        self.assertAlmostEqual(amount, 2150.0)

    def test_basis_is_always_reported(self):
        """The whole contract: a caller cannot get a number without its
        provenance, so the UI cannot accidentally present one as the other."""
        for snapshots in ([], self._snapshots(4), self._snapshots(20)):
            _amount, basis, _weeks = pace(_goal(), snapshots, cashflow_monthly=100.0)
            self.assertIn(basis, (BASIS_BALANCE, BASIS_CASHFLOW))


class ProjectionTests(unittest.TestCase):
    def test_projects_a_hit_date_from_the_pace(self):
        result = projection(_goal(), saved=22200.0, monthly_pace=2000.0, today=date(2026, 9, 1))

        self.assertIsNotNone(result["projected_date"])
        self.assertEqual(result["remaining"], 80000.0 - 22200.0)

    def test_on_pace_when_the_projection_beats_the_target_date(self):
        result = projection(_goal(), saved=70000.0, monthly_pace=5000.0, today=date(2026, 9, 1))
        self.assertTrue(result["on_track"])

    def test_behind_when_the_projection_misses_the_target_date(self):
        result = projection(_goal(), saved=13000.0, monthly_pace=100.0, today=date(2026, 9, 1))
        self.assertFalse(result["on_track"])

    def test_a_zero_pace_has_no_projected_date(self):
        """Dividing by a zero pace would produce infinity, not a date."""
        result = projection(_goal(), saved=1000.0, monthly_pace=0.0, today=date(2026, 9, 1))
        self.assertIsNone(result["projected_date"])
        self.assertIsNone(result["on_track"])

    def test_an_already_met_goal_is_complete(self):
        result = projection(_goal(), saved=80000.0, monthly_pace=2000.0, today=date(2026, 9, 1))
        self.assertTrue(result["is_complete"])
        self.assertEqual(result["remaining"], 0.0)

    def test_a_goal_with_no_target_date_can_still_project(self):
        result = projection(
            _goal(target_date=None), saved=22200.0, monthly_pace=2000.0, today=date(2026, 9, 1)
        )
        self.assertIsNotNone(result["projected_date"])
        # Nothing to be on track *against*.
        self.assertIsNone(result["on_track"])


class WhatIfTests(unittest.TestCase):
    def test_cutting_spending_moves_the_date_earlier(self):
        base = projection(_goal(), saved=22200.0, monthly_pace=2000.0, today=date(2026, 9, 1))
        improved = what_if(
            _goal(),
            saved=22200.0,
            monthly_pace=2000.0,
            monthly_reduction=500.0,
            today=date(2026, 9, 1),
        )

        self.assertIsNotNone(improved["projected_date"])
        self.assertLess(improved["projected_date"], base["projected_date"])

    def test_a_zero_reduction_changes_nothing(self):
        base = projection(_goal(), saved=22200.0, monthly_pace=2000.0, today=date(2026, 9, 1))
        same = what_if(
            _goal(),
            saved=22200.0,
            monthly_pace=2000.0,
            monthly_reduction=0.0,
            today=date(2026, 9, 1),
        )
        self.assertEqual(same["projected_date"], base["projected_date"])

    def test_a_reduction_can_rescue_an_off_pace_goal(self):
        behind = projection(_goal(), saved=40000.0, monthly_pace=1000.0, today=date(2026, 9, 1))
        self.assertFalse(behind["on_track"])

        rescued = what_if(
            _goal(),
            saved=40000.0,
            monthly_pace=1000.0,
            monthly_reduction=4000.0,
            today=date(2026, 9, 1),
        )
        self.assertTrue(rescued["on_track"])


class ContestedTests(unittest.TestCase):
    """Overlap is allowed because it reflects reality, but it must be visible:
    otherwise the dashboard claims you are on track for two things the same
    dollars cannot both buy."""

    def test_no_overlap_means_nothing_contested(self):
        goals = [
            _goal(id=1, account_keys=["plaid:savings"]),
            _goal(id=2, name="Car", account_keys=["plaid:tfsa"]),
        ]
        contested = contested_amounts(goals, {"plaid:savings": 100.0, "plaid:tfsa": 50.0})
        self.assertEqual(contested, {1: 0.0, 2: 0.0})

    def test_a_shared_account_is_contested_for_both_goals(self):
        goals = [
            _goal(id=1, account_keys=["plaid:savings"]),
            _goal(id=2, name="Emergency", account_keys=["plaid:savings"]),
        ]
        contested = contested_amounts(goals, {"plaid:savings": 22200.0})
        self.assertAlmostEqual(contested[1], 22200.0)
        self.assertAlmostEqual(contested[2], 22200.0)

    def test_only_the_shared_portion_counts(self):
        goals = [
            _goal(id=1, account_keys=["plaid:savings", "plaid:tfsa"]),
            _goal(id=2, name="Emergency", account_keys=["plaid:savings"]),
        ]
        contested = contested_amounts(goals, {"plaid:savings": 5000.0, "plaid:tfsa": 17000.0})
        self.assertAlmostEqual(contested[1], 5000.0)
        self.assertAlmostEqual(contested[2], 5000.0)

    def test_a_single_goal_contests_nothing_with_itself(self):
        contested = contested_amounts([_goal(id=1)], {"plaid:savings": 5.0, "plaid:tfsa": 5.0})
        self.assertEqual(contested[1], 0.0)


class ConstantsTests(unittest.TestCase):
    def test_threshold_is_twelve_weeks(self):
        self.assertEqual(BALANCE_BASIS_MIN_WEEKS, 12)


if __name__ == "__main__":
    unittest.main()
