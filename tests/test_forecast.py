"""Phase 32: forward cash-flow projection.

What makes the Budget tab a planning tool rather than a scorecard. Two series:
what you will probably spend, and what you would spend if you held every cap.
The gap between them is the value of sticking to budget — that gap is the point
of the chart.

The properties protected here:

  - **It refuses to project on thin history.** `days_back` defaults to 90, so a
    median over two months is the normal early case, and presenting it as a
    forecast would be a confident-looking guess.
  - **The starting balance is spendable cash.** Including credit (negative) or
    investments (market-driven, not forecastable from transaction history)
    would make a cash-flow projection meaningless.
  - **It degrades rather than blocking.** With no recurring streams detected
    yet, it still projects from trailing medians and says so.
"""

import unittest
from datetime import date
from decimal import Decimal

import pandas as pd

from analytics.forecast import MIN_MONTHS_FOR_FORECAST, project, starting_balance


def _history(months, per_month=1000.0, category="FOOD_AND_DRINK"):
    rows = []
    for month in months:
        year, mon = (int(part) for part in month.split("-"))
        rows.append(
            {
                "month": month,
                "date": pd.Timestamp(date(year, mon, 15)),
                "category": category,
                "tx_type": "expense",
                "adjusted_amount": -per_month,
            }
        )
        rows.append(
            {
                "month": month,
                "date": pd.Timestamp(date(year, mon, 1)),
                "category": "INCOME",
                "tx_type": "income",
                "adjusted_amount": 3000.0,
            }
        )
    return pd.DataFrame(rows)


def _accounts(rows):
    return pd.DataFrame(rows)


class StartingBalanceTests(unittest.TestCase):
    def test_depository_only(self):
        accounts = _accounts(
            [
                {"account_type": "depository", "balance_current": 5000.0},
                {"account_type": "credit", "balance_current": -2000.0},
                {"account_type": "investment", "balance_current": 100000.0},
            ]
        )
        self.assertAlmostEqual(starting_balance(accounts), 5000.0)

    def test_empty_frame_is_zero(self):
        self.assertAlmostEqual(starting_balance(pd.DataFrame()), 0.0)

    def test_missing_column_is_zero_not_an_error(self):
        self.assertAlmostEqual(starting_balance(pd.DataFrame([{"foo": 1}])), 0.0)

    def test_null_balances_are_ignored(self):
        accounts = _accounts(
            [
                {"account_type": "depository", "balance_current": None},
                {"account_type": "depository", "balance_current": 250.0},
            ]
        )
        self.assertAlmostEqual(starting_balance(accounts), 250.0)


class ProjectTests(unittest.TestCase):
    def _four_months(self):
        return _history(["2026-05", "2026-06", "2026-07", "2026-08"])

    def test_refuses_below_the_minimum_history(self):
        frame = _history(["2026-07", "2026-08"])
        result = project(frame, [], {}, starting=1000.0, today=date(2026, 9, 1))

        self.assertFalse(result["has_enough_history"])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["months_of_history"], 2)

    def test_projects_once_there_is_enough_history(self):
        result = project(self._four_months(), [], {}, starting=1000.0, today=date(2026, 9, 1))

        self.assertTrue(result["has_enough_history"])
        self.assertEqual(len(result["rows"]), 6)

    def test_rows_are_wide_not_long(self):
        """This module's API convention: the frontend must never pivot."""
        result = project(self._four_months(), [], {}, starting=1000.0, today=date(2026, 9, 1))

        self.assertEqual(
            set(result["rows"][0]),
            {"month", "projected_balance", "budget_balance", "income", "expenses"},
        )

    def test_horizon_is_six_months_by_default(self):
        result = project(self._four_months(), [], {}, starting=0.0, today=date(2026, 9, 1))
        self.assertEqual([row["month"] for row in result["rows"]][0], "2026-10")
        self.assertEqual(len(result["rows"]), 6)

    def test_horizon_extends_to_cover_a_further_goal_date(self):
        """A goal 14 months out must be visible on the chart it is planned with."""
        result = project(
            self._four_months(),
            [],
            {},
            starting=0.0,
            today=date(2026, 9, 1),
            furthest_goal_date=date(2027, 11, 1),
        )
        self.assertEqual(result["rows"][-1]["month"], "2027-11")

    def test_a_nearer_goal_does_not_shorten_the_horizon(self):
        result = project(
            self._four_months(),
            [],
            {},
            starting=0.0,
            today=date(2026, 9, 1),
            furthest_goal_date=date(2026, 11, 1),
        )
        self.assertEqual(len(result["rows"]), 6)

    def test_balance_accumulates_month_over_month(self):
        result = project(self._four_months(), [], {}, starting=1000.0, today=date(2026, 9, 1))
        balances = [row["projected_balance"] for row in result["rows"]]

        # Income 3000, expenses 1000 -> +2000/month from a 1000 start.
        self.assertAlmostEqual(balances[0], 3000.0)
        self.assertAlmostEqual(balances[1], 5000.0)

    def test_a_recurring_stream_lands_in_its_month(self):
        streams = [
            {
                "stream_id": "local:RENT",
                "merchant_key": "RENT",
                "description": "RENT",
                "direction": "outflow",
                "cadence": "MONTHLY",
                "last_amount": -1500.0,
                "predicted_next_date": date(2026, 10, 1),
                "is_active": True,
            }
        ]
        with_streams = project(self._four_months(), streams, {}, starting=0.0, today=date(2026, 9, 1))
        without = project(self._four_months(), [], {}, starting=0.0, today=date(2026, 9, 1))

        self.assertLess(with_streams["rows"][0]["projected_balance"], without["rows"][0]["projected_balance"])

    def test_degrades_without_streams_and_says_so(self):
        result = project(self._four_months(), [], {}, starting=0.0, today=date(2026, 9, 1))
        self.assertFalse(result["has_recurring_data"])

        streams = [
            {
                "stream_id": "s",
                "merchant_key": "RENT",
                "description": "RENT",
                "direction": "outflow",
                "cadence": "MONTHLY",
                "last_amount": -100.0,
                "predicted_next_date": date(2026, 10, 1),
                "is_active": True,
            }
        ]
        self.assertTrue(
            project(self._four_months(), streams, {}, starting=0.0, today=date(2026, 9, 1))[
                "has_recurring_data"
            ]
        )

    def test_the_budget_series_holds_categories_to_their_caps(self):
        """The gap between the two lines is the value of sticking to budget."""
        caps = {"FOOD_AND_DRINK": Decimal("400")}
        result = project(self._four_months(), [], caps, starting=0.0, today=date(2026, 9, 1))

        row = result["rows"][0]
        # Behaviour spends the 1000 median; the cap holds it to 400.
        self.assertGreater(row["budget_balance"], row["projected_balance"])

    def test_a_cap_above_actual_spending_does_not_inflate_the_budget_line(self):
        """A generous cap is a ceiling, not a target."""
        caps = {"FOOD_AND_DRINK": Decimal("5000")}
        result = project(self._four_months(), [], caps, starting=0.0, today=date(2026, 9, 1))

        row = result["rows"][0]
        self.assertAlmostEqual(row["budget_balance"], row["projected_balance"])

    def test_without_caps_the_two_series_agree(self):
        result = project(self._four_months(), [], {}, starting=0.0, today=date(2026, 9, 1))
        for row in result["rows"]:
            self.assertAlmostEqual(row["budget_balance"], row["projected_balance"])

    def test_an_empty_frame_refuses_rather_than_projecting_zero(self):
        result = project(pd.DataFrame(), [], {}, starting=100.0, today=date(2026, 9, 1))
        self.assertFalse(result["has_enough_history"])

    def test_the_current_partial_month_is_excluded_from_the_baseline(self):
        """September is in progress, so its lower spend must not drag the
        median down and flatter the forecast."""
        frame = pd.concat([self._four_months(), _history(["2026-09"], per_month=10.0)], ignore_index=True)
        result = project(frame, [], {}, starting=0.0, today=date(2026, 9, 15))

        # Median is still ~1000 from the complete months, not pulled toward 10.
        self.assertLess(result["rows"][0]["expenses"], 1100.0)
        self.assertGreater(result["rows"][0]["expenses"], 900.0)

    def test_history_count_reports_complete_months_only(self):
        result = project(self._four_months(), [], {}, starting=0.0, today=date(2026, 9, 1))
        self.assertEqual(result["months_of_history"], 4)

    def test_minimum_history_constant(self):
        self.assertEqual(MIN_MONTHS_FOR_FORECAST, 3)


if __name__ == "__main__":
    unittest.main()


class HorizonClampTests(unittest.TestCase):
    def _four_months(self):
        return _history(["2026-05", "2026-06", "2026-07", "2026-08"])

    def test_a_far_future_goal_cannot_blow_past_the_ceiling(self):
        """Extending to reach a goal is useful; a goal dated 2060 building ~400
        rows to serialize and plot is not."""
        from analytics.forecast import MAX_HORIZON_MONTHS

        result = project(
            self._four_months(),
            [],
            {},
            starting=0.0,
            today=date(2026, 9, 1),
            furthest_goal_date=date(2060, 1, 1),
        )
        self.assertEqual(len(result["rows"]), MAX_HORIZON_MONTHS)


class IncomeBaselineTests(unittest.TestCase):
    def test_months_without_income_count_as_zero(self):
        """Irregular income (freelance, bonuses) must not be read as though it
        arrived every month -- the projected balance would climb faster than
        reality, every month, forever. Expenses already reindex this way."""
        rows = []
        for month in ["2026-05", "2026-06", "2026-07", "2026-08"]:
            year, mon = (int(part) for part in month.split("-"))
            rows.append(
                {
                    "month": month,
                    "date": pd.Timestamp(date(year, mon, 15)),
                    "category": "FOOD_AND_DRINK",
                    "tx_type": "expense",
                    "adjusted_amount": -100.0,
                }
            )
        # Income in only two of the four months.
        for month in ["2026-07", "2026-08"]:
            year, mon = (int(part) for part in month.split("-"))
            rows.append(
                {
                    "month": month,
                    "date": pd.Timestamp(date(year, mon, 1)),
                    "category": "INCOME",
                    "tx_type": "income",
                    "adjusted_amount": 4000.0,
                }
            )

        result = project(pd.DataFrame(rows), [], {}, starting=0.0, today=date(2026, 9, 1))

        # Median over [0, 0, 4000, 4000] is 2000, not 4000.
        self.assertAlmostEqual(result["rows"][0]["income"], 2000.0)
