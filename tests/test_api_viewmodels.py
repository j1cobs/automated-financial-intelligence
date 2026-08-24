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

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import pandas as pd  # noqa: E402

from api.viewmodels import (  # noqa: E402
    DORMANT_DAYS,
    MIN_MONTHLY_INCOME_FOR_RATE,
    SYNC_STALE_DAYS,
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


class EmptyFrameTests(unittest.TestCase):
    def test_builders_tolerate_empty_input(self) -> None:
        empty = pd.DataFrame(
            [], columns=["date", "month", "week", "tx_type", "adjusted_amount", "is_outlier"]
        )
        self.assertEqual(build_overview(empty, pd.DataFrame([]))["savings_rate"], 0.0)
        self.assertEqual(build_cash_flow(empty)["rolling_30d_spend"], [])
        self.assertEqual(build_net_worth(pd.DataFrame([]))["owner_balances"], [])


if __name__ == "__main__":
    unittest.main()
