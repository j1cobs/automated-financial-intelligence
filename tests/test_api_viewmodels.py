"""Unit coverage for the metric fixes in PLAN.md Phase 15 (Fixes 1-8).

These test `api/viewmodels.py`'s builders directly rather than through HTTP, so a
failure points at the arithmetic rather than at FastAPI. `tests/test_api_data.py`
covers the endpoint/auth/shape layer above them.

Each test names the fix it pins. Several assert on behaviour that deliberately differs
from the frozen `app/dashboard.py` — see the divergence table at the end of Phase 15.
"""

from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import pandas as pd  # noqa: E402

from api.viewmodels import (  # noqa: E402
    DORMANT_DAYS,
    MIN_MONTHLY_INCOME_FOR_RATE,
    SPARKLINE_MONTHS,
    SYNC_STALE_DAYS,
    _build_metric,
    build_cash_flow,
    build_net_worth,
    build_overview,
    complete_month_keys,
    prepare_transactions,
)

# Plaid sign convention: positive amount = outflow. A deposit is negative.
_INCOME = -1
_EXPENSE = 1


def _tx(day: str, magnitude: float, direction: int, **overrides):
    row = {
        "date": pd.Timestamp(day),
        "transaction_hash": overrides.get("transaction_hash", f"h-{day}-{magnitude}-{direction}"),
        "account_key": "plaid:chk",
        "account_name": "Chequing",
        "owner_name": "Jacob",
        "account_type": "depository",
        "account_subtype": "checking",
        "description": overrides.get("description", "Thing"),
        "amount": magnitude * direction,
        "category": overrides.get("category", "Shopping"),
        "outlier_score": 0.0,
        "is_outlier": False,
        "is_recurring": False,
        "is_duplicate": False,
    }
    row.update({k: v for k, v in overrides.items() if k in row})
    return row


def _frame(rows) -> pd.DataFrame:
    return prepare_transactions(pd.DataFrame(rows))


def _account(key: str, owner: str, acct_type: str, balance: float, **overrides):
    row = {
        "account_key": key,
        "account_name": overrides.get("account_name", key),
        "official_name": overrides.get("official_name", key),
        "mask": overrides.get("mask", "0000"),
        "owner_name": owner,
        "account_type": acct_type,
        "account_subtype": overrides.get("account_subtype", "checking"),
        "balance_available": balance,
        "balance_current": balance,
        "balance_limit": overrides.get("balance_limit"),
        "manual_credit_limit": overrides.get("manual_credit_limit"),
        "iso_currency_code": "CAD",
        "updated_at": overrides.get("updated_at", pd.Timestamp.now(tz="UTC")),
    }
    return row


class SavingsRateUnitTests(unittest.TestCase):
    """Fix 1 — every ratio the API returns is a fraction, never percentage points."""

    def test_overview_savings_rate_is_a_fraction(self) -> None:
        df = _frame([_tx("2026-05-01", 1000.0, _INCOME), _tx("2026-05-02", 400.0, _EXPENSE)])
        result = build_overview(df, pd.DataFrame([]))
        # 600 saved out of 1000 earned. Percentage points would be 60.0, and the
        # frontend's formatPercent would then render it as "6000.0%".
        self.assertAlmostEqual(result["savings_rate"], 0.6)

    def test_cash_flow_savings_rate_is_a_fraction(self) -> None:
        df = _frame([_tx("2026-05-01", 1000.0, _INCOME), _tx("2026-05-02", 250.0, _EXPENSE)])
        self.assertAlmostEqual(build_cash_flow(df)["savings_rate"], 0.75)

    def test_zero_income_yields_zero_not_a_division_error(self) -> None:
        df = _frame([_tx("2026-05-02", 400.0, _EXPENSE)])
        self.assertEqual(build_overview(df, pd.DataFrame([]))["savings_rate"], 0.0)


class SavingsRateTrendTests(unittest.TestCase):
    """Fix 2 — a month with no meaningful income has no meaningful savings rate."""

    def test_zero_income_month_is_none_not_a_spike(self) -> None:
        df = _frame(
            [
                _tx("2026-04-01", 2000.0, _INCOME),
                _tx("2026-04-05", 500.0, _EXPENSE),
                # May: spending, no income at all.
                _tx("2026-05-05", 300.0, _EXPENSE),
            ]
        )
        trend = {p["month"]: p for p in build_overview(df, pd.DataFrame([]))["savings_rate_trend"]}
        self.assertAlmostEqual(trend["2026-04"]["savings_rate"], 0.75)
        # Frozen Streamlit clips income to 0.01 and reports -3,000,000% here.
        self.assertIsNone(trend["2026-05"]["savings_rate"])
        self.assertEqual(trend["2026-05"]["income"], 0.0)
        self.assertEqual(trend["2026-05"]["expenses"], 300.0)

    def test_income_below_the_floor_is_suppressed(self) -> None:
        df = _frame(
            [
                _tx("2026-05-01", MIN_MONTHLY_INCOME_FOR_RATE - 1, _INCOME),
                _tx("2026-05-05", 900.0, _EXPENSE),
            ]
        )
        trend = build_overview(df, pd.DataFrame([]))["savings_rate_trend"]
        self.assertIsNone(trend[0]["savings_rate"])

    def test_income_at_the_floor_is_reported(self) -> None:
        df = _frame([_tx("2026-05-01", MIN_MONTHLY_INCOME_FOR_RATE, _INCOME)])
        trend = build_overview(df, pd.DataFrame([]))["savings_rate_trend"]
        self.assertAlmostEqual(trend[0]["savings_rate"], 1.0)

    def test_current_month_is_excluded_from_the_trend(self) -> None:
        # The in-progress current month's ratio swings with every new transaction posted
        # (one payday landed, few expenses yet) and looked "random" on the chart; it must
        # not appear in the trend at all. `older` is >1 year back so it can never land in
        # the same calendar month as "today", whenever the test happens to run.
        older = date.today() - timedelta(days=400)
        df = _frame(
            [
                _tx(older.isoformat(), 2000.0, _INCOME),
                _tx((older + timedelta(days=4)).isoformat(), 500.0, _EXPENSE),
                _tx(date.today().isoformat(), 5000.0, _INCOME),
            ]
        )
        trend_months = {p["month"] for p in build_overview(df, pd.DataFrame([]))["savings_rate_trend"]}
        self.assertNotIn(date.today().strftime("%Y-%m"), trend_months)
        self.assertIn(older.strftime("%Y-%m"), trend_months)


class CompleteMonthTests(unittest.TestCase):
    """Fix 3c — partial months must not be averaged in with whole ones."""

    def test_ragged_edges_are_excluded(self) -> None:
        # Jan starts on the 15th and Mar stops on the 20th; only Feb is fully observed.
        df = _frame(
            [
                _tx("2026-01-15", 100.0, _EXPENSE),
                _tx("2026-02-10", 600.0, _EXPENSE),
                _tx("2026-03-20", 100.0, _EXPENSE),
            ]
        )
        self.assertEqual(complete_month_keys(df), {"2026-02"})

    def test_monthly_average_uses_only_complete_months(self) -> None:
        df = _frame(
            [
                _tx("2026-01-15", 100.0, _EXPENSE),
                _tx("2026-02-10", 600.0, _EXPENSE),
                _tx("2026-03-20", 100.0, _EXPENSE),
            ]
        )
        result = build_overview(df, pd.DataFrame([]))
        # Averaging all three months gives 266.67 and understates a real month.
        self.assertAlmostEqual(result["avg_monthly_expense"], 600.0)
        self.assertEqual(result["complete_months"], 1)

    def test_avg_monthly_net_is_derived_from_the_monthly_averages(self) -> None:
        df = _frame(
            [
                _tx("2026-01-15", 50.0, _EXPENSE),
                _tx("2026-02-01", 1000.0, _INCOME),
                _tx("2026-02-10", 400.0, _EXPENSE),
                _tx("2026-03-20", 50.0, _EXPENSE),
            ]
        )
        result = build_overview(df, pd.DataFrame([]))
        # Fix 3a: this tile used the ALL-TIME net_flow while sitting between two
        # monthly tiles, so it grew with the length of history.
        self.assertAlmostEqual(result["avg_monthly_net"], 600.0)
        self.assertNotAlmostEqual(result["avg_monthly_net"], result["net_flow"])


class OwnerBalanceTests(unittest.TestCase):
    """Fix 4 — one row per holder, not one per account."""

    def _accounts(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                _account("a1", "Jacob", "depository", 1000.0),
                _account("a2", "Jacob", "credit", 200.0, account_subtype="credit card"),
                _account("a3", "Alexie", "depository", 500.0),
            ]
        )

    def test_one_row_per_owner(self) -> None:
        rows = build_net_worth(self._accounts())["owner_balances"]
        self.assertEqual([r["owner"] for r in rows], ["Jacob", "Alexie"])

    def test_credit_is_negated_and_net_is_summed(self) -> None:
        rows = {r["owner"]: r for r in build_net_worth(self._accounts())["owner_balances"]}
        jacob = rows["Jacob"]
        self.assertAlmostEqual(jacob["depository"], 1000.0)
        self.assertAlmostEqual(jacob["credit"], -200.0)
        self.assertAlmostEqual(jacob["net"], 800.0)

    def test_per_account_detail_is_preserved_for_the_tooltip(self) -> None:
        rows = {r["owner"]: r for r in build_net_worth(self._accounts())["owner_balances"]}
        self.assertEqual(len(rows["Jacob"]["accounts"]), 2)
        self.assertEqual(len(rows["Alexie"]["accounts"]), 1)


class OwnerBalanceShortNameTests(unittest.TestCase):
    """Item 4 — short server-computed account names, mask-disambiguated only when an
    owner has more than one account of the same subtype."""

    def _accounts(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                # Jacob has two credit cards -- same subtype label, must collide and
                # get mask-disambiguated.
                _account(
                    "a1",
                    "Jacob",
                    "credit",
                    200.0,
                    account_subtype="credit card",
                    mask="3265",
                ),
                _account(
                    "a2",
                    "Jacob",
                    "credit",
                    50.0,
                    account_subtype="credit card",
                    mask="8496",
                ),
                # Alexie has a single TFSA -- no collision, stays plain.
                _account("a3", "Alexie", "investment", 500.0, account_subtype="tfsa"),
            ]
        )

    def test_colliding_accounts_get_mask_disambiguated_names(self) -> None:
        rows = {r["owner"]: r for r in build_net_worth(self._accounts())["owner_balances"]}
        short_names = {a["short_name"] for a in rows["Jacob"]["accounts"]}
        self.assertEqual(short_names, {"Credit card Jacob ••••3265", "Credit card Jacob ••••8496"})
        # The two names must actually differ from each other.
        self.assertEqual(len(short_names), 2)

    def test_single_account_of_a_subtype_stays_plain(self) -> None:
        rows = {r["owner"]: r for r in build_net_worth(self._accounts())["owner_balances"]}
        alexie_names = [a["short_name"] for a in rows["Alexie"]["accounts"]]
        self.assertEqual(alexie_names, ["TFSA Alexie"])


class StaleAndDormantTests(unittest.TestCase):
    """Fix 5 — sync health and dormancy are different questions."""

    def test_stale_uses_the_balance_refresh_timestamp(self) -> None:
        now = pd.Timestamp.now(tz="UTC")
        acct = pd.DataFrame(
            [
                _account("fresh", "Jacob", "depository", 10.0, updated_at=now),
                _account(
                    "stale",
                    "Jacob",
                    "depository",
                    10.0,
                    updated_at=now - pd.Timedelta(days=SYNC_STALE_DAYS + 2),
                ),
            ]
        )
        names = [a["account_key"] for a in build_net_worth(acct)["stale_accounts"]]
        self.assertEqual(names, ["stale"])

    def test_a_recently_refreshed_account_is_not_stale_at_three_days(self) -> None:
        # The frozen Streamlit threshold is 3 days, which flagged nearly everything.
        now = pd.Timestamp.now(tz="UTC")
        acct = pd.DataFrame(
            [_account("a", "Jacob", "depository", 10.0, updated_at=now - pd.Timedelta(days=3))]
        )
        self.assertEqual(build_net_worth(acct)["stale_accounts"], [])

    def test_dormant_uses_last_transaction_and_needs_a_balance(self) -> None:
        old = (pd.Timestamp.today().normalize() - pd.Timedelta(days=DORMANT_DAYS + 10)).strftime("%Y-%m-%d")
        tx = _frame([_tx(old, 10.0, _EXPENSE, transaction_hash="old")])
        tx["account_key"] = "sleepy"
        acct = pd.DataFrame([_account("sleepy", "Jacob", "depository", 250.0)])
        dormant = build_net_worth(acct, tx)["dormant_accounts"]
        self.assertEqual(len(dormant), 1)
        self.assertEqual(dormant[0]["account_key"], "sleepy")
        self.assertGreaterEqual(dormant[0]["days_inactive"], DORMANT_DAYS)

    def test_empty_dormant_account_is_not_reported(self) -> None:
        old = (pd.Timestamp.today().normalize() - pd.Timedelta(days=DORMANT_DAYS + 10)).strftime("%Y-%m-%d")
        tx = _frame([_tx(old, 10.0, _EXPENSE, transaction_hash="old")])
        tx["account_key"] = "sleepy"
        acct = pd.DataFrame([_account("sleepy", "Jacob", "depository", 0.0)])
        self.assertEqual(build_net_worth(acct, tx)["dormant_accounts"], [])


class CashFlowShapeTests(unittest.TestCase):
    """Fixes 6 and 8 — wide series rows, and expenses as a positive magnitude."""

    def test_month_over_month_is_wide_and_lowercase(self) -> None:
        df = _frame([_tx("2026-05-01", 1000.0, _INCOME), _tx("2026-05-02", 400.0, _EXPENSE)])
        rows = build_cash_flow(df)["month_over_month"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0].keys()), {"month", "income", "expenses", "net"})
        self.assertAlmostEqual(rows[0]["income"], 1000.0)
        self.assertAlmostEqual(rows[0]["expenses"], 400.0)
        self.assertAlmostEqual(rows[0]["net"], 600.0)

    def test_weekly_trend_is_wide_too(self) -> None:
        df = _frame([_tx("2026-05-01", 100.0, _EXPENSE)])
        rows = build_cash_flow(df)["weekly_trend"]
        self.assertEqual(set(rows[0].keys()), {"week", "income", "expenses", "net"})

    def test_expenses_are_positive_and_match_build_overview(self) -> None:
        df = _frame([_tx("2026-05-01", 1000.0, _INCOME), _tx("2026-05-02", 400.0, _EXPENSE)])
        cash = build_cash_flow(df)
        overview = build_overview(df, pd.DataFrame([]))
        self.assertGreater(cash["expenses"], 0)
        self.assertAlmostEqual(cash["expenses"], overview["expenses"])
        self.assertAlmostEqual(cash["net_flow"], overview["net_flow"])


class RollingSpendTests(unittest.TestCase):
    """Fix 7 — a 30-day window must mean 30 calendar days, not 30 rows."""

    def test_window_is_calendar_days_not_rows(self) -> None:
        # Two expenses 59 days apart. A 30-ROW window sees both (there are only two
        # rows); a 30-DAY window ending on the later date must see only the later one.
        df = _frame(
            [
                _tx("2026-01-01", 100.0, _EXPENSE, transaction_hash="a"),
                _tx("2026-03-01", 200.0, _EXPENSE, transaction_hash="b"),
            ]
        )
        series = build_cash_flow(df)["rolling_30d_spend"]
        last = series[-1]
        self.assertEqual(last["date"], "2026-03-01")
        self.assertAlmostEqual(last["amount"], 200.0)

    def test_quiet_days_report_zero_rather_than_carrying_old_spend(self) -> None:
        df = _frame(
            [
                _tx("2026-01-01", 100.0, _EXPENSE, transaction_hash="a"),
                _tx("2026-03-01", 200.0, _EXPENSE, transaction_hash="b"),
            ]
        )
        by_date = {p["date"]: p for p in build_cash_flow(df)["rolling_30d_spend"]}
        # More than 30 days after the January charge and before the March one.
        self.assertAlmostEqual(by_date["2026-02-15"]["amount"], 0.0)

    def test_leading_partial_window_is_dropped(self) -> None:
        df = _frame(
            [
                _tx("2026-01-01", 100.0, _EXPENSE, transaction_hash="a"),
                _tx("2026-03-01", 200.0, _EXPENSE, transaction_hash="b"),
            ]
        )
        series = build_cash_flow(df)["rolling_30d_spend"]
        # The series starts a full window in, so every point covers 30 real days.
        self.assertEqual(series[0]["date"], "2026-01-30")

    def test_daily_average_accompanies_the_total(self) -> None:
        df = _frame([_tx("2026-01-01", 300.0, _EXPENSE)])
        point = build_cash_flow(df)["rolling_30d_spend"][-1]
        self.assertAlmostEqual(point["daily_avg"], point["amount"] / 30)

    def test_short_history_still_returns_a_series(self) -> None:
        # Less than one full window of data: a short line beats an empty chart.
        df = _frame(
            [
                _tx("2026-01-01", 10.0, _EXPENSE, transaction_hash="a"),
                _tx("2026-01-05", 10.0, _EXPENSE, transaction_hash="b"),
            ]
        )
        self.assertTrue(build_cash_flow(df)["rolling_30d_spend"])


class MetricBaselineTests(unittest.TestCase):
    """Fix 12 — every headline figure ships with the baseline that makes it legible."""

    def _two_years(self) -> pd.DataFrame:
        # Six complete months, expenses climbing 100 -> 600.
        rows = []
        for i, month in enumerate(["01", "02", "03", "04", "05", "06"], start=1):
            rows.append(_tx(f"2026-{month}-02", 1000.0, _INCOME, transaction_hash=f"i{month}"))
            rows.append(_tx(f"2026-{month}-15", i * 100.0, _EXPENSE, transaction_hash=f"e{month}"))
            # Boundary coverage so each month counts as complete.
            rows.append(_tx(f"2026-{month}-01", 1.0, _EXPENSE, transaction_hash=f"a{month}"))
            rows.append(_tx(f"2026-{month}-28", 1.0, _EXPENSE, transaction_hash=f"z{month}"))
        return _frame(rows)

    def test_every_headline_metric_carries_context(self) -> None:
        metrics = build_overview(self._two_years(), pd.DataFrame([]))["metrics"]
        self.assertEqual(
            set(metrics),
            {"avg_monthly_income", "avg_monthly_expense", "avg_monthly_net", "savings_rate"},
        )
        for key, metric in metrics.items():
            with self.subTest(key=key):
                self.assertEqual(metric["key"], key)
                self.assertIsNotNone(metric["baseline"])
                self.assertGreater(metric["baseline_months"], 0)
                self.assertTrue(metric["sparkline"])

    def test_sparkline_is_chronological_and_capped(self) -> None:
        metric = build_overview(self._two_years(), pd.DataFrame([]))["metrics"]["avg_monthly_expense"]
        spark = metric["sparkline"]
        self.assertLessEqual(len(spark), SPARKLINE_MONTHS)
        # Expenses climb month over month, so the series must too — if it came back
        # unsorted the sparkline would draw a meaningless shape.
        self.assertEqual(spark, sorted(spark))

    def test_delta_is_zero_when_the_period_is_all_history(self) -> None:
        # Comparing every complete month against the average of those same months.
        metric = build_overview(self._two_years(), pd.DataFrame([]))["metrics"]["avg_monthly_expense"]
        self.assertAlmostEqual(metric["delta_pct"], 0.0, places=6)

    def test_delta_sign_survives_a_negative_baseline(self) -> None:
        # Net flow is routinely negative. Dividing by a signed baseline would invert the
        # comparison exactly when someone is overspending, reporting "improving" for a
        # month that got worse.
        metric = _build_metric("net", -50.0, pd.Series({"2026-01": -100.0, "2026-02": -100.0}))
        self.assertAlmostEqual(metric["baseline"], -100.0)
        # -50 is ABOVE -100 (less negative), so the delta must be positive.
        self.assertGreater(metric["delta_pct"], 0)

    def test_absent_history_yields_no_baseline_rather_than_a_fake_one(self) -> None:
        metric = _build_metric("x", 42.0, pd.Series(dtype=float))
        self.assertIsNone(metric["baseline"])
        self.assertIsNone(metric["delta_pct"])
        self.assertEqual(metric["sparkline"], [])

    def test_zero_baseline_does_not_divide(self) -> None:
        metric = _build_metric("x", 10.0, pd.Series({"2026-01": 0.0}))
        self.assertIsNone(metric["delta_pct"])

    def test_savings_rate_baseline_skips_no_income_months(self) -> None:
        df = _frame(
            [
                _tx("2026-01-02", 1000.0, _INCOME, transaction_hash="i1"),
                _tx("2026-01-03", 500.0, _EXPENSE, transaction_hash="e1"),
                _tx("2026-01-28", 1.0, _EXPENSE, transaction_hash="z1"),
                # February: spending, no income. Must not drag the baseline to -infinity.
                _tx("2026-02-01", 300.0, _EXPENSE, transaction_hash="e2"),
                _tx("2026-02-28", 1.0, _EXPENSE, transaction_hash="z2"),
            ]
        )
        metric = build_overview(df, pd.DataFrame([]))["metrics"]["savings_rate"]
        self.assertIsNotNone(metric["baseline"])
        self.assertGreater(metric["baseline"], -1.0)


class EmptyFrameTests(unittest.TestCase):
    def test_builders_tolerate_empty_input(self) -> None:
        empty = pd.DataFrame(
            [], columns=["date", "month", "week", "tx_type", "adjusted_amount", "is_outlier"]
        )
        self.assertEqual(build_overview(empty, pd.DataFrame([]))["savings_rate"], 0.0)
        self.assertEqual(build_cash_flow(empty)["rolling_30d_spend"], [])
        self.assertEqual(build_net_worth(pd.DataFrame([]))["owner_balances"], [])


def _month_start(months_ago: int):
    """The 1st of a calendar month `months_ago` months before today, as a date."""
    period = pd.Period(date.today(), freq="M") - months_ago
    return period.start_time.date()


def _history_point(day_offset_iso: str, net_worth: float) -> dict[str, Any]:
    """A `get_net_worth_history()`-shaped row. `net_worth_trend_monthly`'s resampling
    loop reads `liabilities`/`liquid_cash` off every snapshot even when a given test
    only cares about `net_worth`/`date`, so every fixture needs the full shape or it
    raises a KeyError deep inside `build_overview`."""
    return {
        "date": day_offset_iso,
        "net_worth": net_worth,
        "assets": net_worth,
        "liabilities": 0.0,
        "liquid_cash": net_worth,
    }


class OverviewHomeInsightsTests(unittest.TestCase):
    """Phase 23 -- the retired Home tab's insights (recurring spend, merchant
    breakdown, cash-flow projection, net-worth trend/mom-delta, category drift) were
    folded into `build_overview`. Category drift is no longer its own list -- it now
    lives on `month_over_month`'s `usual`/`this_month_drift_pct`/`last_month_drift_pct`
    fields (one row per category, wide). The standalone `recurring_monthly_spend` tile
    and subscription detection were dropped as product features entirely, not
    renamed/reshaped -- there is no replacement coverage for either below.
    """

    def test_empty_df_returns_the_static_empty_result_even_with_net_worth_history(self) -> None:
        # Discrepancy vs. the old build_home: build_overview's `df.empty` guard
        # short-circuits to a hardcoded empty dict BEFORE `net_worth_history` is
        # consulted at all, so a caller whose *period-filtered* frame happens to be
        # empty loses the net-worth trend even when real snapshot history exists.
        # build_home never had this coupling (its two params were independent). Pinning
        # the actual behaviour here since this is what the shipped code now does.
        empty = pd.DataFrame(
            [], columns=["date", "month", "tx_type", "adjusted_amount", "description", "is_recurring"]
        )
        history = [_history_point("2026-08-20", 1000.0)]
        result = build_overview(empty, pd.DataFrame([]), empty, history)
        self.assertEqual(result["net_worth_trend_daily"], [])
        self.assertEqual(result["recurring_items"], [])
        self.assertEqual(result["top_merchants"], [])
        self.assertIsNone(result["cash_flow_projection"])

    def test_recurring_items_lists_only_flagged_expenses(self) -> None:
        baseline = _month_start(2)
        # Spread across the month (day 1 and day 28) so its observed span covers the
        # whole month and `complete_month_keys` counts it -- a single-day span
        # wouldn't, since coverage is measured against the dataset's own date range.
        df = _frame(
            [
                _tx(
                    baseline.isoformat(),
                    50.0,
                    _EXPENSE,
                    description="Gym Membership",
                    is_recurring=True,
                ),
                # Not flagged recurring -- must not count toward the recurring total.
                _tx(
                    baseline.replace(day=28).isoformat(),
                    900.0,
                    _EXPENSE,
                    description="New Laptop",
                    is_recurring=False,
                ),
            ]
        )
        result = build_overview(df, pd.DataFrame([]), df, [])
        self.assertEqual(result["recurring_items"], [{"description": "Gym Membership", "amount": 50.0}])
        # `recurring_monthly_spend` (a single float) backed a Home-tab tile removed
        # from the product in Phase 23 -- no replacement key, nothing to assert here.

    def test_top_merchants_aggregates_by_description_within_trailing_12_months(self) -> None:
        baseline = _month_start(2)
        df = _frame(
            [
                _tx(baseline.isoformat(), 40.0, _EXPENSE, description="Amazon"),
                _tx(baseline.isoformat(), 60.0, _EXPENSE, description="Amazon"),
                _tx(baseline.isoformat(), 10.0, _EXPENSE, description="Coffee Shop"),
            ]
        )
        result = build_overview(df, pd.DataFrame([]), df, [])
        self.assertEqual(
            result["top_merchants"][0],
            {"description": "Amazon", "amount": 100.0},
        )

    def test_cash_flow_projection_present_only_for_the_current_month(self) -> None:
        today = date.today()
        df = _frame(
            [
                _tx(today.isoformat(), 1000.0, _INCOME),
                _tx(today.isoformat(), 100.0, _EXPENSE),
            ]
        )
        result = build_overview(df, pd.DataFrame([]), df, [])
        projection = result["cash_flow_projection"]
        self.assertIsNotNone(projection)
        self.assertEqual(projection["month"], today.strftime("%Y-%m"))
        self.assertAlmostEqual(projection["spent_so_far"], 100.0)
        self.assertAlmostEqual(projection["income_so_far"], 1000.0)
        self.assertEqual(projection["days_elapsed"], today.day)
        # Projected figures scale up by (days_in_month / days_elapsed) >= 1.
        self.assertGreaterEqual(projection["projected_expenses"], projection["spent_so_far"])

    def test_cash_flow_projection_is_none_without_current_month_data(self) -> None:
        baseline = _month_start(3)
        df = _frame([_tx(baseline.isoformat(), 100.0, _EXPENSE)])
        result = build_overview(df, pd.DataFrame([]), df, [])
        self.assertIsNone(result["cash_flow_projection"])

    def test_month_over_month_drift_uses_the_users_own_baseline(self) -> None:
        # Groceries has two complete baseline months (100/mo) then spikes to 140 this
        # month -- this is the old "category drift" test, rewritten against
        # `month_over_month`'s wide `usual`/`this_month_drift_pct` fields (Phase 23
        # folded category drift into that list instead of keeping it separate).
        m3 = _month_start(3)
        m2 = _month_start(2)
        today = date.today()
        df = _frame(
            [
                _tx(m3.isoformat(), 50.0, _EXPENSE, category="Groceries", transaction_hash="g1a"),
                _tx(m3.replace(day=28).isoformat(), 50.0, _EXPENSE, category="Groceries", transaction_hash="g1b"),
                _tx(m2.isoformat(), 50.0, _EXPENSE, category="Groceries", transaction_hash="g2a"),
                _tx(m2.replace(day=28).isoformat(), 50.0, _EXPENSE, category="Groceries", transaction_hash="g2b"),
                _tx(today.isoformat(), 140.0, _EXPENSE, category="Groceries", transaction_hash="g3"),
                # First seen this month -- no historical baseline to drift against.
                _tx(today.isoformat(), 50.0, _EXPENSE, category="Brand New Category", transaction_hash="b1"),
            ]
        )
        result = build_overview(df, pd.DataFrame([]), df, [])
        mom = {row["category"]: row for row in result["month_over_month"]}
        self.assertAlmostEqual(mom["Groceries"]["usual"], 100.0)
        self.assertAlmostEqual(mom["Groceries"]["this_month"], 140.0)
        self.assertAlmostEqual(mom["Groceries"]["this_month_drift_pct"], 0.4)
        self.assertIsNone(mom["Brand New Category"]["usual"])
        self.assertIsNone(mom["Brand New Category"]["this_month_drift_pct"])

    def test_biggest_expense_this_month_picks_largest_by_absolute_amount(self) -> None:
        today = date.today()
        df = _frame(
            [
                _tx(today.isoformat(), 25.0, _EXPENSE, description="Coffee"),
                _tx(today.isoformat(), 400.0, _EXPENSE, description="Rent Top-Up"),
                _tx(today.isoformat(), 60.0, _EXPENSE, description="Groceries"),
            ]
        )
        result = build_overview(df, pd.DataFrame([]), df, [])
        biggest = result["biggest_expense_this_month"]
        self.assertIsNotNone(biggest)
        self.assertEqual(biggest["description"], "Rent Top-Up")
        self.assertAlmostEqual(biggest["amount"], 400.0)
        self.assertEqual(biggest["date"], today.isoformat())

    def test_biggest_expense_this_month_is_none_without_current_month_expenses(self) -> None:
        baseline = _month_start(3)
        df = _frame([_tx(baseline.isoformat(), 50.0, _EXPENSE)])
        result = build_overview(df, pd.DataFrame([]), df, [])
        self.assertIsNone(result["biggest_expense_this_month"])

    def test_net_worth_mom_delta_uses_closest_point_at_least_one_month_prior(self) -> None:
        today = date.today()
        history = [
            _history_point((today - timedelta(days=95)).isoformat(), 1000.0),
            # Closest point that is still >= 1 month before `today` -- must be picked
            # over the (wrong) naive "second-to-last sample" approach.
            _history_point((today - timedelta(days=40)).isoformat(), 1200.0),
            _history_point((today - timedelta(days=10)).isoformat(), 1500.0),
            _history_point(today.isoformat(), 1600.0),
        ]
        # Needs a non-empty df/all_time_df -- an empty one short-circuits before
        # net_worth_history is even read (see the discrepancy test above).
        df = _frame([_tx(today.isoformat(), 10.0, _EXPENSE)])
        result = build_overview(df, pd.DataFrame([]), df, history)
        self.assertAlmostEqual(result["net_worth_mom_delta"], 1600.0 - 1200.0)

    def test_net_worth_mom_delta_is_none_with_a_single_trend_point(self) -> None:
        history = [_history_point(date.today().isoformat(), 500.0)]
        df = _frame([_tx(date.today().isoformat(), 10.0, _EXPENSE)])
        result = build_overview(df, pd.DataFrame([]), df, history)
        self.assertIsNone(result["net_worth_mom_delta"])

    def test_upcoming_recurring_projects_next_charge_from_median_interval(self) -> None:
        base = date.today() - timedelta(days=90)
        gaps = [29, 31, 30]
        occurrence_dates = [base]
        for gap in gaps:
            occurrence_dates.append(occurrence_dates[-1] + timedelta(days=gap))
        rows = [
            _tx(d.isoformat(), 12.99, _EXPENSE, description="Music Streaming", is_recurring=True)
            for d in occurrence_dates
        ]
        df = _frame(rows)
        result = build_overview(df, pd.DataFrame([]), df, [])
        upcoming = {row["description"]: row for row in result["upcoming_recurring"]}
        self.assertIn("Music Streaming", upcoming)
        last_date = occurrence_dates[-1]
        expected_next = last_date + timedelta(days=30)
        actual_next = date.fromisoformat(upcoming["Music Streaming"]["next_expected_date"])
        self.assertLessEqual(abs((actual_next - expected_next).days), 2)
        self.assertEqual(upcoming["Music Streaming"]["typical_interval_days"], 30)

    def test_upcoming_recurring_excludes_single_occurrence(self) -> None:
        df = _frame(
            [_tx(date.today().isoformat(), 9.99, _EXPENSE, description="One Timer", is_recurring=True)]
        )
        result = build_overview(df, pd.DataFrame([]), df, [])
        descriptions = [row["description"] for row in result["upcoming_recurring"]]
        self.assertNotIn("One Timer", descriptions)

    def test_upcoming_recurring_uses_median_not_mean_interval(self) -> None:
        # Gaps: 30, 30, 30, then one deliberately-skewed 90-day gap (a missed/late
        # charge). Mean interval would be inflated by the outlier (45 days); the
        # median stays at 30. Distinguishing the two is the point of this test.
        base = date.today() - timedelta(days=180)
        gaps = [30, 30, 30, 90]
        occurrence_dates = [base]
        for gap in gaps:
            occurrence_dates.append(occurrence_dates[-1] + timedelta(days=gap))
        rows = [
            _tx(d.isoformat(), 8.0, _EXPENSE, description="Skewed Gap Sub", is_recurring=True)
            for d in occurrence_dates
        ]
        df = _frame(rows)
        result = build_overview(df, pd.DataFrame([]), df, [])
        upcoming = {row["description"]: row for row in result["upcoming_recurring"]}
        self.assertEqual(upcoming["Skewed Gap Sub"]["typical_interval_days"], 30)


if __name__ == "__main__":
    unittest.main()
