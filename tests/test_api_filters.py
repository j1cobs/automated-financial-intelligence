"""Coverage for `api/filters.py` — PLAN.md Phase 15, Fix 9.

`api/filters.py` is a hand-written port of `app/dashboard.py::_build_sidebar_filters`,
which is frozen and therefore cannot be shared. The two can drift silently; this file is
the thing that notices. Tests are grouped by the invariant they defend, and the
non-obvious ones name the Streamlit line they mirror.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import pandas as pd  # noqa: E402

from api.filters import (  # noqa: E402
    DashboardFilters,
    apply_filters,
    build_filter_options,
    preset_month_keys,
)
from api.viewmodels import prepare_transactions  # noqa: E402


def _row(day: str, amount: float, **overrides):
    row = {
        "date": pd.Timestamp(day),
        "transaction_hash": overrides.get("transaction_hash", f"h-{day}-{amount}"),
        "account_key": overrides.get("account_key", "plaid:chk"),
        "account_name": overrides.get("account_name", "Chequing"),
        "owner_name": overrides.get("owner_name", "Jacob"),
        "account_type": overrides.get("account_type", "depository"),
        "account_subtype": "checking",
        "description": overrides.get("description", "Thing"),
        "amount": amount,
        "category": overrides.get("category", "Shopping"),
        "outlier_score": overrides.get("outlier_score", 0.0),
        "is_outlier": overrides.get("is_outlier", False),
        "is_recurring": False,
        "is_duplicate": False,
    }
    return row


def _frame(rows) -> pd.DataFrame:
    return prepare_transactions(pd.DataFrame(rows))


def _filters(**kwargs) -> DashboardFilters:
    return DashboardFilters(**kwargs)


class PeriodPresetTests(unittest.TestCase):
    """The period selects whole months, anchored to the latest transaction."""

    def _spread(self) -> pd.DataFrame:
        return _frame(
            [
                _row("2026-01-10", 10.0, transaction_hash="a"),
                _row("2026-02-10", 10.0, transaction_hash="b"),
                _row("2026-03-15", 10.0, transaction_hash="c"),
            ]
        )

    def test_anchored_to_latest_transaction_not_today(self) -> None:
        # Today is months after 2026-03-15. Anchoring the window to `today` would put
        # every row outside it and blank the dashboard whenever ingestion stalls;
        # anchoring to the latest transaction keeps showing the most recent real data.
        keys = preset_month_keys("last_30_days", self._spread())
        self.assertEqual(keys, {"2026-03"})

    def test_all_time_returns_every_month(self) -> None:
        self.assertEqual(preset_month_keys("all_time", self._spread()), {"2026-01", "2026-02", "2026-03"})

    def test_current_month_is_the_latest_months(self) -> None:
        self.assertEqual(preset_month_keys("current_month", self._spread()), {"2026-03"})

    def test_period_admits_whole_months_not_a_date_range(self) -> None:
        # "Last 30 days" from 2026-03-15 reaches back to 2026-02-14. The Feb 20 row falls
        # inside that window, which puts 2026-02 among the selected months — and February
        # is then admitted IN FULL, pulling in the Feb 1 row that the 30-day window itself
        # excludes. Deliberate, not a bug: every downstream aggregate groups by month, and
        # showing half a month's spend as a month is worse than a slightly wide window.
        df = _frame(
            [
                _row("2026-02-01", 10.0, transaction_hash="early_feb"),
                _row("2026-02-20", 10.0, transaction_hash="late_feb"),
                _row("2026-03-15", 10.0, transaction_hash="march"),
            ]
        )
        filtered, _ = apply_filters(df, _filters(period="last_30_days"))
        self.assertEqual(set(filtered["transaction_hash"]), {"early_feb", "late_feb", "march"})

    def test_custom_period_uses_explicit_month_keys(self) -> None:
        filtered, _ = apply_filters(self._spread(), _filters(period="custom", months=["2026-01"]))
        self.assertEqual(set(filtered["transaction_hash"]), {"a"})

    def test_empty_frame_is_handled(self) -> None:
        empty = pd.DataFrame([], columns=["date", "month"])
        self.assertEqual(preset_month_keys("last_30_days", empty), set())


class TwoFrameTests(unittest.TestCase):
    """Invariant 1 — trend charts must not collapse when the period narrows."""

    def test_all_time_frame_ignores_the_period(self) -> None:
        df = _frame(
            [
                _row("2026-01-10", 10.0, transaction_hash="a"),
                _row("2026-03-15", 10.0, transaction_hash="c"),
            ]
        )
        filtered, all_time = apply_filters(df, _filters(period="current_month"))
        self.assertEqual(set(filtered["transaction_hash"]), {"c"})
        self.assertEqual(set(all_time["transaction_hash"]), {"a", "c"})

    def test_all_time_frame_still_honours_non_date_filters(self) -> None:
        df = _frame(
            [
                _row("2026-01-10", 10.0, transaction_hash="a", owner_name="Jacob"),
                _row("2026-01-11", 10.0, transaction_hash="b", owner_name="Alexie"),
            ]
        )
        _filtered, all_time = apply_filters(df, _filters(period="all_time", owners=["Jacob"]))
        self.assertEqual(set(all_time["transaction_hash"]), {"a"})


class EnrichBeforeFilterTests(unittest.TestCase):
    """Invariant 2 — the most subtle one, and the one a careless refactor breaks."""

    def test_transfer_stays_classified_when_the_other_leg_is_filtered_out(self) -> None:
        # A transfer between two of your own accounts: outflow from one, inflow to the
        # other, same amount, same day. Pair matching runs during enrichment, over the
        # complete frame. Filter to only one account afterwards and the surviving leg
        # must still read "transfer" — if enrichment ran after filtering, the matcher
        # would never see the partner row and would misread this as a real expense,
        # inflating spending by the size of every internal transfer.
        df = _frame(
            [
                _row("2026-05-01", 500.0, transaction_hash="out", account_key="A", account_name="A"),
                _row("2026-05-01", -500.0, transaction_hash="in", account_key="B", account_name="B"),
            ]
        )
        self.assertEqual(set(df["tx_type"]), {"transfer"})

        filtered, _ = apply_filters(df, _filters(period="all_time", accounts=["A"]))
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["tx_type"], "transfer")


class NonDateFilterTests(unittest.TestCase):
    def _mixed(self) -> pd.DataFrame:
        return _frame(
            [
                _row(
                    "2026-05-01",
                    10.0,
                    transaction_hash="a",
                    owner_name="Jacob",
                    category="Groceries",
                    account_name="Chequing",
                    description="Loblaws",
                ),
                _row(
                    "2026-05-02",
                    500.0,
                    transaction_hash="b",
                    owner_name="Alexie",
                    category="Travel",
                    account_name="Visa",
                    description="Air Canada",
                    is_outlier=True,
                ),
            ]
        )

    def test_owner_filter(self) -> None:
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time", owners=["Jacob"]))
        self.assertEqual(set(filtered["transaction_hash"]), {"a"})

    def test_category_filter(self) -> None:
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time", categories=["Travel"]))
        self.assertEqual(set(filtered["transaction_hash"]), {"b"})

    def test_account_filter(self) -> None:
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time", accounts=["Visa"]))
        self.assertEqual(set(filtered["transaction_hash"]), {"b"})

    def test_outliers_only(self) -> None:
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time", outliers_only=True))
        self.assertEqual(set(filtered["transaction_hash"]), {"b"})

    def test_amount_range_uses_absolute_value(self) -> None:
        filtered, _ = apply_filters(
            self._mixed(), _filters(period="all_time", amount_min=100.0, amount_max=1000.0)
        )
        self.assertEqual(set(filtered["transaction_hash"]), {"b"})

    def test_inverted_amount_range_returns_rows(self) -> None:
        # Mirrors app/dashboard.py:768 — tolerate the mistake instead of showing nothing.
        filtered, _ = apply_filters(
            self._mixed(), _filters(period="all_time", amount_min=1000.0, amount_max=100.0)
        )
        self.assertEqual(set(filtered["transaction_hash"]), {"b"})

    def test_search_is_case_insensitive(self) -> None:
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time", search="loblaws"))
        self.assertEqual(set(filtered["transaction_hash"]), {"a"})

    def test_search_is_literal_not_regex(self) -> None:
        # Streamlit leaves str.contains in regex mode; over HTTP an unbalanced paren
        # would be a 500 rather than "no matches".
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time", search="("))
        self.assertEqual(len(filtered), 0)

    def test_filters_compose(self) -> None:
        filtered, _ = apply_filters(
            self._mixed(), _filters(period="all_time", owners=["Jacob"], categories=["Travel"])
        )
        self.assertEqual(len(filtered), 0)

    def test_no_filters_returns_everything(self) -> None:
        filtered, _ = apply_filters(self._mixed(), _filters(period="all_time"))
        self.assertEqual(len(filtered), 2)


class DuplicatesOnlyTests(unittest.TestCase):
    def test_groups_on_account_key_not_account_name(self) -> None:
        # Two DIFFERENT accounts that happen to share a display name. Grouping on the
        # name would call these duplicates of each other; they are not.
        # Mirrors app/dashboard.py:788-792.
        df = _frame(
            [
                _row(
                    "2026-05-01",
                    50.0,
                    transaction_hash="a",
                    account_key="A",
                    account_name="Chequing",
                ),
                _row(
                    "2026-05-01",
                    50.0,
                    transaction_hash="b",
                    account_key="B",
                    account_name="Chequing",
                ),
            ]
        )
        filtered, _ = apply_filters(df, _filters(period="all_time", duplicates_only=True))
        self.assertEqual(len(filtered), 0)

    def test_real_repeats_on_one_account_are_surfaced(self) -> None:
        df = _frame(
            [
                _row("2026-05-01", 250.0, transaction_hash="a", account_key="A"),
                _row("2026-05-01", 250.0, transaction_hash="b", account_key="A"),
            ]
        )
        filtered, _ = apply_filters(df, _filters(period="all_time", duplicates_only=True))
        self.assertEqual(set(filtered["transaction_hash"]), {"a", "b"})


class FilterOptionTests(unittest.TestCase):
    def test_options_are_derived_and_sorted(self) -> None:
        df = _frame(
            [
                _row("2026-01-10", 10.0, transaction_hash="a", owner_name="Jacob", category="Zoo"),
                _row(
                    "2026-02-10",
                    -90.0,
                    transaction_hash="b",
                    owner_name="Alexie",
                    category="Apples",
                    account_name="Visa",
                ),
            ]
        )
        options = build_filter_options(df)
        self.assertEqual(options["owners"], ["Alexie", "Jacob"])
        self.assertEqual(options["categories"], ["Apples", "Zoo"])
        self.assertEqual(options["accounts"], ["Chequing", "Visa"])
        self.assertEqual([m["key"] for m in options["months"]], ["2026-01", "2026-02"])
        self.assertEqual(options["months"][0]["label"], "January 2026")
        # Bounds are absolute values, matching how the amount filter compares.
        self.assertAlmostEqual(options["amount_min"], 10.0)
        self.assertAlmostEqual(options["amount_max"], 90.0)

    def test_empty_frame_gives_empty_options(self) -> None:
        options = build_filter_options(pd.DataFrame([]))
        self.assertEqual(options["owners"], [])
        self.assertEqual(options["amount_max"], 0.0)


class DefaultsTests(unittest.TestCase):
    def test_default_period_is_three_months(self) -> None:
        self.assertEqual(DashboardFilters().period, "last_3_months")

    def test_is_default_detects_an_untouched_filter_set(self) -> None:
        self.assertTrue(DashboardFilters().is_default())
        self.assertFalse(DashboardFilters(owners=["Jacob"]).is_default())
        self.assertFalse(DashboardFilters(period="all_time").is_default())


if __name__ == "__main__":
    unittest.main()
