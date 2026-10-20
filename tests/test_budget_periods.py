"""Phase 28: per-month budget caps with carry-forward inheritance.

The distinction these tests exist to protect is **absent vs zero**. A category
with no cap anywhere is "no budget set"; a category capped at 0 is "I have
committed to spending nothing here". Collapsing them would make an unset
category render as an instantly-breached $0 budget.
"""

import re
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from analytics.budget_periods import previous_period, resolve_caps
from database.db import DatabaseClient

MIGRATION = Path(__file__).resolve().parent.parent / "database" / "migrations" / "026_budget_periods.sql"


def _mock_connect(fetchall_return=None, rowcount=0):
    """Same shape as tests/test_db_upserts.py::_mock_connect."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall_return if fetchall_return is not None else []
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    connection = MagicMock()
    connection.cursor.return_value = cursor
    connection.__enter__.return_value = connection
    connection.__exit__.return_value = False

    return MagicMock(return_value=connection), cursor


def row(category: str, period: str, limit) -> dict:
    return {"category": category, "period": period, "monthly_limit": limit}


class ResolveCapsTests(unittest.TestCase):
    def test_empty_rows_yield_no_caps(self):
        self.assertEqual(resolve_caps([], "2026-09"), {})

    def test_explicit_cap_for_the_requested_period(self):
        caps = resolve_caps([row("FOOD_AND_DRINK", "2026-09", 400)], "2026-09")
        self.assertEqual(caps, {"FOOD_AND_DRINK": Decimal("400")})

    def test_inherits_the_most_recent_earlier_cap(self):
        rows = [row("FOOD_AND_DRINK", "2026-08", 400)]
        caps = resolve_caps(rows, "2026-09")
        self.assertEqual(caps, {"FOOD_AND_DRINK": Decimal("400")})

    def test_inherits_across_a_multi_month_gap(self):
        rows = [row("FOOD_AND_DRINK", "2026-03", 400)]
        caps = resolve_caps(rows, "2026-09")
        self.assertEqual(caps, {"FOOD_AND_DRINK": Decimal("400")})

    def test_nearest_earlier_cap_wins_over_an_older_one(self):
        rows = [
            row("FOOD_AND_DRINK", "2026-03", 400),
            row("FOOD_AND_DRINK", "2026-08", 300),
        ]
        caps = resolve_caps(rows, "2026-09")
        self.assertEqual(caps, {"FOOD_AND_DRINK": Decimal("300")})

    def test_a_later_cap_does_not_leak_backwards(self):
        """Editing October must not change what September was budgeted at."""
        rows = [
            row("FOOD_AND_DRINK", "2026-08", 400),
            row("FOOD_AND_DRINK", "2026-10", 300),
        ]
        self.assertEqual(resolve_caps(rows, "2026-09")["FOOD_AND_DRINK"], Decimal("400"))
        self.assertEqual(resolve_caps(rows, "2026-10")["FOOD_AND_DRINK"], Decimal("300"))

    def test_category_whose_first_cap_is_later_is_absent_not_zero(self):
        rows = [row("FOOD_AND_DRINK", "2026-10", 300)]
        caps = resolve_caps(rows, "2026-09")
        self.assertNotIn("FOOD_AND_DRINK", caps)

    def test_zero_is_a_real_cap_and_is_preserved(self):
        rows = [row("ENTERTAINMENT", "2026-09", 0)]
        caps = resolve_caps(rows, "2026-09")
        self.assertIn("ENTERTAINMENT", caps)
        self.assertEqual(caps["ENTERTAINMENT"], Decimal("0"))

    def test_zero_is_inherited_like_any_other_cap(self):
        rows = [row("ENTERTAINMENT", "2026-07", 0)]
        caps = resolve_caps(rows, "2026-09")
        self.assertEqual(caps["ENTERTAINMENT"], Decimal("0"))

    def test_categories_resolve_independently(self):
        rows = [
            row("FOOD_AND_DRINK", "2026-08", 400),
            row("TRANSPORTATION", "2026-09", 250),
            row("TRAVEL", "2026-11", 900),
        ]
        caps = resolve_caps(rows, "2026-09")
        self.assertEqual(
            caps,
            {"FOOD_AND_DRINK": Decimal("400"), "TRANSPORTATION": Decimal("250")},
        )

    def test_accepts_float_and_decimal_limits(self):
        rows = [row("MEDICAL", "2026-09", 125.5), row("TRAVEL", "2026-09", Decimal("75.25"))]
        caps = resolve_caps(rows, "2026-09")
        self.assertEqual(caps["MEDICAL"], Decimal("125.5"))
        self.assertEqual(caps["TRAVEL"], Decimal("75.25"))

    def test_row_order_does_not_matter(self):
        ascending = [
            row("FOOD_AND_DRINK", "2026-03", 400),
            row("FOOD_AND_DRINK", "2026-08", 300),
        ]
        self.assertEqual(
            resolve_caps(ascending, "2026-09"),
            resolve_caps(list(reversed(ascending)), "2026-09"),
        )

    def test_rejects_a_malformed_period(self):
        with self.assertRaises(ValueError):
            resolve_caps([], "2026-9")
        with self.assertRaises(ValueError):
            resolve_caps([], "September 2026")


class PreviousPeriodTests(unittest.TestCase):
    def test_steps_back_one_month(self):
        self.assertEqual(previous_period("2026-09"), "2026-08")

    def test_wraps_across_the_year_boundary(self):
        self.assertEqual(previous_period("2026-01"), "2025-12")

    def test_rejects_a_malformed_period(self):
        with self.assertRaises(ValueError):
            previous_period("2026-13")


class MigrationSeedGuardTests(unittest.TestCase):
    """ensure_schema() re-runs every .sql on every call, so the one-time seed
    must be guarded. Without the guard, clearing a cap and running the pipeline
    silently brings it back. The SQL cannot be executed here (the DB layer is
    mocked repo-wide), so these pin the guard's presence against removal."""

    def setUp(self):
        self.sql = MIGRATION.read_text(encoding="utf-8")

    def test_migration_exists(self):
        self.assertTrue(MIGRATION.is_file())

    def test_table_creation_is_re_runnable(self):
        self.assertIn("CREATE TABLE IF NOT EXISTS budget_periods", self.sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS", self.sql)

    def test_unique_on_category_and_period(self):
        self.assertRegex(self.sql, r"UNIQUE\s*\(\s*category\s*,\s*period\s*\)")

    def test_seed_is_guarded_on_a_persistent_marker(self):
        """Guarding on an empty `budget_periods` was not enough: clearing the
        last remaining cap empties the table and the seed re-fires. The marker
        records that the upgrade happened, which stays true regardless of what
        the user later deletes.

        The behaviour itself is pinned by
        `tests/test_migrations_execute.py::test_the_seed_does_not_resurrect_a_cleared_cap`,
        which executes this SQL. These string assertions only guard against the
        clause being dropped when no database is available.
        """
        normalized = re.sub(r"\s+", " ", self.sql)
        self.assertIn(
            "WHERE NOT EXISTS (SELECT 1 FROM schema_seeds WHERE name = 'budget_periods_from_budgets')",
            normalized,
            "the one-time seed must not re-run, or a cleared cap is resurrected",
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS schema_seeds", normalized)

    def test_seed_cannot_collide(self):
        self.assertIn("ON CONFLICT (category, period) DO NOTHING", self.sql)

    def test_does_not_write_to_the_legacy_budgets_table(self):
        """`budgets` is Streamlit-owned: it reads AND writes that table, so any
        write from this path would discard budgets saved from Streamlit."""
        statements = [s.strip().upper() for s in self.sql.split(";")]
        writes = [
            s
            for s in statements
            if re.match(r"^(INSERT|UPDATE|DELETE)\b", s) and re.search(r"\bBUDGETS\b", s)
        ]
        # The seed SELECTs from budgets; it must never INSERT/UPDATE/DELETE it.
        for statement in writes:
            self.assertNotRegex(
                statement,
                r"^(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+BUDGETS\b",
            )


class BudgetPeriodDbTests(unittest.TestCase):
    def test_get_budget_periods_strips_char_padding(self):
        connect, cursor = _mock_connect([("FOOD_AND_DRINK", "2026-09", 400.0)])
        with patch("database.db.psycopg.connect", connect):
            rows = DatabaseClient("postgresql://x/y").get_budget_periods()

        self.assertEqual(rows, [{"category": "FOOD_AND_DRINK", "period": "2026-09", "monthly_limit": 400.0}])
        self.assertIn("FROM budget_periods", cursor.execute.call_args[0][0])

    def test_get_budget_periods_handles_blank_padded_char_column(self):
        """`period` is CHAR(7); Postgres blank-pads it. resolve_caps compares
        periods as strings, so a trailing space would break inheritance."""
        connect, _ = _mock_connect([("TRAVEL", "2026-09 ", 900.0)])
        with patch("database.db.psycopg.connect", connect):
            rows = DatabaseClient("postgresql://x/y").get_budget_periods()

        self.assertEqual(rows[0]["period"], "2026-09")

    def test_upsert_targets_the_category_period_pair(self):
        client = DatabaseClient("postgresql://x/y")
        with patch.object(client, "_execute_many") as execute_many:
            client.upsert_budget_period("FOOD_AND_DRINK", "2026-10", 300.0)

        sql, params = execute_many.call_args[0]
        self.assertIn("ON CONFLICT (category, period) DO UPDATE", sql)
        self.assertEqual(params, [("FOOD_AND_DRINK", "2026-10", 300.0)])

    def test_delete_reports_whether_a_row_went(self):
        connect, _ = _mock_connect(rowcount=1)
        with patch("database.db.psycopg.connect", connect):
            self.assertTrue(DatabaseClient("postgresql://x/y").delete_budget_period("TRAVEL", "2026-10"))

        connect, _ = _mock_connect(rowcount=0)
        with patch("database.db.psycopg.connect", connect):
            self.assertFalse(DatabaseClient("postgresql://x/y").delete_budget_period("TRAVEL", "2026-10"))


if __name__ == "__main__":
    unittest.main()


class BuildBudgetPeriodTests(unittest.TestCase):
    """build_budget's contract at the boundary the UI depends on."""

    def _frame(self, rows):
        import pandas as pd

        return pd.DataFrame(rows)

    def _rows(self, month="2026-09"):
        return [
            {
                "month": month,
                "tx_type": "expense",
                "category": "FOOD_AND_DRINK",
                "adjusted_amount": -120.0,
                "pfc_detailed": "FOOD_AND_DRINK_GROCERIES",
            },
            {
                "month": month,
                "tx_type": "expense",
                "category": "FOOD_AND_DRINK",
                "adjusted_amount": -80.0,
                "pfc_detailed": "FOOD_AND_DRINK_RESTAURANT",
            },
        ]

    def test_absent_cap_is_none_not_zero(self):
        from api.viewmodels import build_budget

        result = build_budget(self._frame(self._rows()), [], period="2026-09")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertIsNone(item["limit"])
        self.assertIsNone(item["pct"])
        self.assertFalse(item["is_over_budget"])

    def test_zero_cap_is_a_real_cap_and_is_breached_by_any_spend(self):
        from api.viewmodels import build_budget

        caps = [{"category": "FOOD_AND_DRINK", "period": "2026-09", "monthly_limit": 0}]
        result = build_budget(self._frame(self._rows()), caps, period="2026-09")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertEqual(item["limit"], 0.0)
        self.assertTrue(item["is_over_budget"])
        self.assertEqual(item["pct"], 1.0)

    def test_inherited_cap_names_its_source_month(self):
        from api.viewmodels import build_budget

        caps = [{"category": "FOOD_AND_DRINK", "period": "2026-07", "monthly_limit": 400}]
        result = build_budget(self._frame(self._rows()), caps, period="2026-09")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertTrue(item["is_inherited"])
        self.assertEqual(item["inherited_from"], "2026-07")

    def test_explicit_cap_is_not_marked_inherited(self):
        from api.viewmodels import build_budget

        caps = [{"category": "FOOD_AND_DRINK", "period": "2026-09", "monthly_limit": 400}]
        result = build_budget(self._frame(self._rows()), caps, period="2026-09")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertFalse(item["is_inherited"])
        self.assertIsNone(item["inherited_from"])

    def test_detail_breakdown_sums_to_the_category_total(self):
        from api.viewmodels import build_budget

        result = build_budget(self._frame(self._rows()), [], period="2026-09")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertEqual(
            sorted(d["pfc_detailed"] for d in item["details"]),
            ["FOOD_AND_DRINK_GROCERIES", "FOOD_AND_DRINK_RESTAURANT"],
        )
        self.assertAlmostEqual(sum(d["amount"] for d in item["details"]), item["spent"])

    def test_detail_breakdown_keeps_rows_with_no_plaid_detail(self):
        """Otherwise the parts silently stop summing to the whole."""
        from api.viewmodels import build_budget

        rows = self._rows()
        rows.append(
            {
                "month": "2026-09",
                "tx_type": "expense",
                "category": "FOOD_AND_DRINK",
                "adjusted_amount": -20.0,
                "pfc_detailed": None,
            }
        )
        result = build_budget(self._frame(rows), [], period="2026-09")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertIn(None, [d["pfc_detailed"] for d in item["details"]])
        self.assertAlmostEqual(sum(d["amount"] for d in item["details"]), item["spent"])

    def test_requested_month_selects_that_month_not_the_latest(self):
        from api.viewmodels import build_budget

        rows = self._rows("2026-08") + self._rows("2026-09")
        result = build_budget(self._frame(rows), [], period="2026-08")
        self.assertEqual(result["month"], "2026-08")
        item = next(i for i in result["items"] if i["category"] == "FOOD_AND_DRINK")
        self.assertAlmostEqual(item["spent"], 200.0)
