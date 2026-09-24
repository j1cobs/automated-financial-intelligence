"""The migrations, executed by an actual Postgres.

This suite exists because `tests/test_budget_periods.py` cannot do this job. Its
`MigrationSeedGuardTests` assert the seed guard by regex over the SQL *text*, and
say so in their own docstring ("The SQL cannot be executed here"). A regex cannot
tell you whether the statement it matched can run -- and migration 026 could not:
it read `MIN(t.date)` where the column is `transaction_date`, took down every
entry point that calls `ensure_schema()` (`api/main.py:33`,
`pipeline/runner.py:115`, `scripts/seed_sample_data.py:278`), and did it with the
whole suite green.

Note that `ensure_schema()` runs all 29 files on one connection and commits only
after the last, so one bad file means *none* of them applied. The blast radius of
a typo in migration 026 is migrations 001-029.

Skipped unless `MIGRATION_TEST_DATABASE_URL` is set -- see `tests/pg_support.py`.
"""

from __future__ import annotations

import unittest

from tests.pg_support import PostgresBackedTestCase, table_names

#: Every table the 29 migrations are expected to leave behind. Listed explicitly
#: rather than counted, so a migration that silently stops creating its table is
#: a failure and not just a different number.
EXPECTED_TABLES = {
    "accounts",
    "categories",
    "transactions",
    "budgets",
    "pipeline_runs",
    "oauth_pending_state",
    "account_balance_snapshots",
    "plaid_sync_state",
    "merchant_categories",
    # Phases 28-34 -- the four migrations that had never run.
    "budget_periods",
    "recurring_streams",
    "savings_goals",
    "savings_goal_accounts",
    "anomalies",
    "anomaly_feedback",
}


class EnsureSchemaExecutionTests(PostgresBackedTestCase):
    migrate_in_setup = False

    def test_ensure_schema_runs_against_postgres(self):
        """The one that goes red on the `t.date` bug.

        Postgres resolves column references at parse-analysis time, so this fails
        on an empty database too -- the seed does not need to match a row for the
        bad reference to raise.
        """
        self.client().ensure_schema()

    def test_ensure_schema_is_idempotent(self):
        """CLAUDE.md calls this load-bearing; until now it was only asserted as a
        string. Every `.sql` re-runs on every call, so a second call must be a
        no-op rather than an error."""
        client = self.client()
        client.ensure_schema()
        client.ensure_schema()

    def test_every_expected_table_exists(self):
        self.client().ensure_schema()
        self.assertLessEqual(EXPECTED_TABLES, table_names(self.admin_url))

    def test_a_second_run_does_not_duplicate_rows(self):
        """Idempotency is about data as well as DDL: the seeded category list in
        migration 023 must not double."""
        client = self.client()
        client.ensure_schema()
        first = self.execute("SELECT count(*) FROM categories")[0][0]
        client.ensure_schema()
        self.assertEqual(self.execute("SELECT count(*) FROM categories")[0][0], first)


class LegacyBudgetSeedTests(PostgresBackedTestCase):
    """Migration 026's seed: one row per legacy `budgets` cap, at the earliest
    month present in `transactions`. Carry-forward then covers every later month,
    which is what reproduces the old "this limit always applies" behaviour."""

    migrate_in_setup = False

    def _seed_legacy_state(self, with_transactions: bool = True):
        """Reconstruct a pre-026 database: legacy `budgets` rows, seed never run.

        Clearing `schema_seeds` is what makes this a real upgrade rather than a
        no-op -- that marker is precisely the record of "this one-time seed has
        already happened", and a database predating this migration has none.
        """
        client = self.client()
        client.ensure_schema()
        if with_transactions:
            self.seed_account()
            self.seed_transaction("hash-older", "2026-03-15", "OLDER", -20.00)
            self.seed_transaction("hash-newer", "2026-07-02", "NEWER", -35.00)
        self.execute(
            "INSERT INTO budgets (category, monthly_limit) VALUES (%s, %s)",
            ("FOOD_AND_DRINK", 400.00),
        )
        self.execute("DELETE FROM budget_periods")
        self.execute("DELETE FROM schema_seeds")
        return client

    def test_the_seed_lands_at_the_earliest_transaction_month(self):
        """Pins the *semantics* of the fixed line, not merely that it parses:
        `MIN(transaction_date)` must pick March, not July or today."""
        client = self._seed_legacy_state()
        client.ensure_schema()

        rows = self.execute("SELECT category, period, monthly_limit FROM budget_periods")
        self.assertEqual(len(rows), 1)
        category, period, limit = rows[0]
        self.assertEqual(category, "FOOD_AND_DRINK")
        self.assertEqual(period.strip(), "2026-03")
        self.assertEqual(float(limit), 400.00)

    def test_the_seed_does_not_resurrect_a_cleared_cap(self):
        """The guard, tested for real.

        Deletes the *only* cap, which is the case a `NOT EXISTS (SELECT 1 FROM
        budget_periods)` guard misses: the table is empty again, so the seed
        re-fires and the cleared cap returns. Executing the SQL is the only way
        to see this; a regex over the statement text cannot.
        """
        client = self._seed_legacy_state()
        client.ensure_schema()
        self.execute("DELETE FROM budget_periods WHERE category = 'FOOD_AND_DRINK'")

        client.ensure_schema()

        self.assertEqual(self.execute("SELECT count(*) FROM budget_periods")[0][0], 0)

    def test_the_marker_survives_so_the_seed_never_runs_twice(self):
        client = self._seed_legacy_state()
        client.ensure_schema()
        self.assertEqual(
            self.execute("SELECT count(*) FROM schema_seeds WHERE name = 'budget_periods_from_budgets'")[0][
                0
            ],
            1,
        )

    def test_the_seed_does_not_write_to_the_legacy_budgets_table(self):
        """`budgets` is Streamlit-owned: `app/dashboard.py` reads it at :1116 and
        writes it at :1186. Any write from this path discards what Streamlit saved."""
        client = self._seed_legacy_state()
        before = self.execute("SELECT category, monthly_limit FROM budgets ORDER BY category")
        client.ensure_schema()
        self.assertEqual(
            self.execute("SELECT category, monthly_limit FROM budgets ORDER BY category"),
            before,
        )

    def test_an_empty_transactions_table_falls_back_to_the_current_month(self):
        """Legacy caps but no history yet; the COALESCE arm must hold."""
        client = self._seed_legacy_state(with_transactions=False)

        client.ensure_schema()

        rows = self.execute("SELECT period FROM budget_periods")
        self.assertEqual(len(rows), 1)
        self.assertRegex(rows[0][0].strip(), r"^\d{4}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
