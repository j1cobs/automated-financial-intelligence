"""`DatabaseClient`'s Phase 28-35 SQL, executed by an actual Postgres.

Every other test of this layer mocks `psycopg` and asserts on the SQL *string*
handed to it. That checks the Python around the query and nothing about the query
itself -- which is how migration 026 shipped reading a column that does not
exist. These methods were written in the same session, against the same mocks, so
their SQL carries the same unverified status until something runs it.

Write-then-read, because a method that writes what it cannot read back is broken
in the way that matters. Skipped unless `MIGRATION_TEST_DATABASE_URL` is set.
"""

from __future__ import annotations

import datetime as dt
import unittest

from tests.pg_support import PostgresBackedTestCase


class BudgetPeriodRoundTripTests(PostgresBackedTestCase):
    def test_upsert_then_read_back(self):
        client = self.client()
        client.upsert_budget_period("FOOD_AND_DRINK", "2026-09", 400.00)

        rows = client.get_budget_periods()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["category"], "FOOD_AND_DRINK")
        self.assertEqual(rows[0]["period"], "2026-09")
        self.assertAlmostEqual(rows[0]["monthly_limit"], 400.00)

    def test_period_comes_back_unpadded(self):
        """`period` is CHAR(7), which Postgres blank-pads. resolve_caps compares
        periods as strings, so a stray space silently breaks carry-forward."""
        client = self.client()
        client.upsert_budget_period("TRANSPORT", "2026-10", 150.00)

        self.assertEqual(client.get_budget_periods()[0]["period"], "2026-10")

    def test_re_upserting_updates_in_place(self):
        client = self.client()
        client.upsert_budget_period("TRANSPORT", "2026-10", 150.00)
        client.upsert_budget_period("TRANSPORT", "2026-10", 225.00)

        rows = client.get_budget_periods()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["monthly_limit"], 225.00)

    def test_editing_one_month_leaves_its_neighbours_alone(self):
        client = self.client()
        client.upsert_budget_period("TRANSPORT", "2026-09", 150.00)
        client.upsert_budget_period("TRANSPORT", "2026-10", 999.00)

        by_period = {r["period"]: r["monthly_limit"] for r in client.get_budget_periods()}
        self.assertAlmostEqual(by_period["2026-09"], 150.00)

    def test_delete_reports_whether_it_removed_anything(self):
        client = self.client()
        client.upsert_budget_period("TRANSPORT", "2026-10", 150.00)

        self.assertTrue(client.delete_budget_period("TRANSPORT", "2026-10"))
        self.assertFalse(client.delete_budget_period("TRANSPORT", "2026-10"))
        self.assertEqual(client.get_budget_periods(), [])


class RecurringStreamRoundTripTests(PostgresBackedTestCase):
    def _stream(self, **overrides):
        stream = {
            "stream_id": "local:NETFLIX.COM",
            "merchant_key": "NETFLIX.COM",
            "description": "NETFLIX.COM",
            "category": "ENTERTAINMENT",
            "cadence": "MONTHLY",
            "direction": "outflow",
            "last_amount": -16.99,
            "last_date": dt.date(2026, 9, 2),
            "predicted_next_date": dt.date(2026, 10, 2),
            "status": "mature",
            "source": "local",
            "is_active": True,
        }
        stream.update(overrides)
        return stream

    def test_upsert_then_read_back(self):
        client = self.client()
        client.upsert_recurring_streams([self._stream()])

        rows = client.get_recurring_streams()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stream_id"], "local:NETFLIX.COM")
        self.assertEqual(rows[0]["cadence"], "MONTHLY")
        self.assertAlmostEqual(rows[0]["last_amount"], -16.99)
        self.assertEqual(rows[0]["predicted_next_date"], dt.date(2026, 10, 2))

    def test_re_detection_updates_rather_than_duplicating(self):
        """Idempotency across pipeline runs, which is why `stream_id` has to be
        stable in `analytics.recurring`."""
        client = self.client()
        client.upsert_recurring_streams([self._stream()])
        client.upsert_recurring_streams([self._stream(last_amount=-22.99)])

        rows = client.get_recurring_streams()
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["last_amount"], -22.99)

    def test_active_only_filters_and_can_be_turned_off(self):
        client = self.client()
        client.upsert_recurring_streams(
            [self._stream(), self._stream(stream_id="local:GONE", is_active=False)]
        )

        self.assertEqual(len(client.get_recurring_streams()), 1)
        self.assertEqual(len(client.get_recurring_streams(active_only=False)), 2)

    def test_optional_fields_may_be_absent(self):
        """The Plaid and local paths populate different subsets; NULLs must not
        trip the NOT NULL columns or the read."""
        client = self.client()
        client.upsert_recurring_streams(
            [
                {
                    "stream_id": "local:SPARSE",
                    "merchant_key": "SPARSE",
                    "description": "SPARSE",
                    "direction": "outflow",
                }
            ]
        )

        row = client.get_recurring_streams(active_only=False)[0]
        self.assertIsNone(row["cadence"])
        self.assertIsNone(row["predicted_next_date"])
        self.assertEqual(row["source"], "local")


class StreamMembershipTests(PostgresBackedTestCase):
    """The stream-toggle path: Phase 31's fix for "the same charge can be checked
    recurring over and over". Membership is resolved in Python via
    `analytics.categorizer.merchant_key`, so this crosses the SQL/Python seam and
    a mock cannot tell you it works."""

    def setUp(self):
        super().setUp()
        self.seed_account()
        self.seed_transaction("h1", "2026-07-02", "NETFLIX.COM", -16.99)
        self.seed_transaction("h2", "2026-08-02", "NETFLIX.COM", -16.99)
        self.seed_transaction("h3", "2026-08-05", "SOME GROCER", -52.10)
        self.client().upsert_recurring_streams(
            [
                {
                    "stream_id": "local:NETFLIX.COM",
                    "merchant_key": "NETFLIX.COM",
                    "description": "NETFLIX.COM",
                    "direction": "outflow",
                }
            ]
        )

    def test_hashes_for_stream_finds_its_members_only(self):
        hashes = self.client().transaction_hashes_for_stream("local:NETFLIX.COM")
        self.assertEqual(sorted(hashes), ["h1", "h2"])

    def test_an_unknown_stream_matches_nothing(self):
        self.assertEqual(self.client().transaction_hashes_for_stream("local:NOPE"), [])

    def test_toggling_a_stream_moves_every_member_row(self):
        changed = self.client().update_recurring_for_stream("local:NETFLIX.COM", True)

        self.assertEqual(changed, 2)
        flagged = self.execute(
            "SELECT transaction_hash FROM transactions WHERE is_recurring ORDER BY transaction_hash"
        )
        self.assertEqual([r[0] for r in flagged], ["h1", "h2"])


class SavingsGoalRoundTripTests(PostgresBackedTestCase):
    def setUp(self):
        super().setUp()
        self.seed_account("test:savings")

    def test_create_then_read_back_with_links(self):
        client = self.client()
        goal_id = client.create_savings_goal(
            "Down payment", 80000.0, dt.date(2027, 6, 1), ["test:savings"], 22200.0
        )

        goals = client.get_savings_goals()

        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["id"], goal_id)
        self.assertEqual(goals[0]["name"], "Down payment")
        self.assertEqual(goals[0]["account_keys"], ["test:savings"])
        self.assertAlmostEqual(goals[0]["baseline_amount"], 22200.0)

    def test_a_goal_without_a_target_date_is_allowed_and_sorts_last(self):
        client = self.client()
        client.create_savings_goal("Someday", 1000.0, None, [], 0.0)
        client.create_savings_goal("Soon", 500.0, dt.date(2026, 12, 1), [], 0.0)

        self.assertEqual([g["name"] for g in client.get_savings_goals()], ["Soon", "Someday"])

    def test_archived_goals_are_hidden_unless_asked_for(self):
        client = self.client()
        goal_id = client.create_savings_goal("Old", 100.0, None, [], 0.0)
        client.update_savings_goal(goal_id, is_archived=True)

        self.assertEqual(client.get_savings_goals(), [])
        self.assertEqual(len(client.get_savings_goals(include_archived=True)), 1)

    def test_update_replaces_account_links_wholesale(self):
        client = self.client()
        self.seed_account("test:other")
        goal_id = client.create_savings_goal("Car", 20000.0, None, ["test:savings"], 0.0)

        client.update_savings_goal(goal_id, account_keys=["test:other"])

        self.assertEqual(client.get_savings_goals()[0]["account_keys"], ["test:other"])

    def test_delete_cascades_to_the_links(self):
        client = self.client()
        goal_id = client.create_savings_goal("Car", 20000.0, None, ["test:savings"], 0.0)

        self.assertTrue(client.delete_savings_goal(goal_id))
        self.assertFalse(client.delete_savings_goal(goal_id))
        self.assertEqual(self.execute("SELECT count(*) FROM savings_goal_accounts")[0][0], 0)

    def test_two_goals_may_share_an_account(self):
        """Overlap is allowed on purpose -- it is surfaced as a contested amount
        rather than forbidden, so no UNIQUE may creep onto account_key."""
        client = self.client()
        client.create_savings_goal("A", 1000.0, None, ["test:savings"], 0.0)
        client.create_savings_goal("B", 2000.0, None, ["test:savings"], 0.0)

        self.assertEqual(
            [g["account_keys"] for g in client.get_savings_goals()],
            [["test:savings"], ["test:savings"]],
        )


class GoalBalanceHistoryTests(PostgresBackedTestCase):
    def test_sums_linked_accounts_per_day_oldest_first(self):
        self.seed_account("test:savings")
        self.seed_account("test:tfsa")
        for key, day, balance in [
            ("test:savings", "2026-08-01", 1000.0),
            ("test:tfsa", "2026-08-01", 500.0),
            ("test:savings", "2026-09-01", 1200.0),
        ]:
            self.execute(
                "INSERT INTO account_balance_snapshots (account_key, snapshot_date, "
                "balance_current) VALUES (%s, %s, %s)",
                (key, day, balance),
            )

        history = self.client().get_goal_balance_history(["test:savings", "test:tfsa"])

        self.assertEqual([h["snapshot_date"] for h in history], [dt.date(2026, 8, 1), dt.date(2026, 9, 1)])
        self.assertAlmostEqual(history[0]["balance"], 1500.0)

    def test_no_accounts_means_no_query(self):
        self.assertEqual(self.client().get_goal_balance_history([]), [])


class AnomalyRoundTripTests(PostgresBackedTestCase):
    def _anomaly(self, **overrides):
        row = {
            "kind": "category_drift",
            "subject": "FOOD_AND_DRINK",
            "period": "2026-09",
            "severity": "medium",
            "explanation": "FOOD_AND_DRINK is $310.00 so far, 63% above your usual $190.00.",
        }
        row.update(overrides)
        return row

    def test_upsert_then_read_back(self):
        client = self.client()
        client.upsert_anomalies([self._anomaly()])

        rows = client.get_anomalies()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["subject"], "FOOD_AND_DRINK")
        self.assertEqual(rows[0]["period"], "2026-09")

    def test_re_detection_updates_severity_but_preserves_detected_at(self):
        """The alert stays current as the month develops; when it first tripped
        is history and must not move."""
        client = self.client()
        client.upsert_anomalies([self._anomaly()])
        first_detected = self.execute("SELECT detected_at FROM anomalies")[0][0]

        client.upsert_anomalies([self._anomaly(severity="high", explanation="worse now")])

        rows = client.get_anomalies()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["severity"], "high")
        self.assertEqual(self.execute("SELECT detected_at FROM anomalies")[0][0], first_detected)

    def test_high_sorts_above_medium(self):
        """`severity` is TEXT, so `ORDER BY severity DESC` would put 'medium'
        above 'high'. The query uses an explicit CASE rank instead."""
        client = self.client()
        client.upsert_anomalies(
            [
                self._anomaly(subject="AAA_MEDIUM", severity="medium"),
                self._anomaly(subject="ZZZ_HIGH", severity="high"),
            ]
        )

        self.assertEqual([r["subject"] for r in client.get_anomalies()], ["ZZZ_HIGH", "AAA_MEDIUM"])

    def test_dismissal_hides_that_period_only(self):
        client = self.client()
        client.upsert_anomalies([self._anomaly(period="2026-09"), self._anomaly(period="2026-10")])

        client.dismiss_anomaly("category_drift", "FOOD_AND_DRINK", "2026-09")

        self.assertEqual([r["period"] for r in client.get_anomalies()], ["2026-10"])

    def test_dismissal_is_idempotent_and_reversible(self):
        client = self.client()
        client.upsert_anomalies([self._anomaly()])
        client.dismiss_anomaly("category_drift", "FOOD_AND_DRINK", "2026-09")
        client.dismiss_anomaly("category_drift", "FOOD_AND_DRINK", "2026-09")

        self.assertEqual(client.get_anomalies(), [])
        self.assertEqual(len(client.get_anomaly_feedback()), 1)

        client.restore_anomaly("category_drift", "FOOD_AND_DRINK", "2026-09")
        self.assertEqual(len(client.get_anomalies()), 1)

    def test_filtering_by_period_still_excludes_dismissals(self):
        client = self.client()
        client.upsert_anomalies([self._anomaly()])
        client.dismiss_anomaly("category_drift", "FOOD_AND_DRINK", "2026-09")

        self.assertEqual(client.get_anomalies(period="2026-09"), [])

    def test_feedback_period_comes_back_unpadded(self):
        client = self.client()
        client.dismiss_anomaly("category_drift", "FOOD_AND_DRINK", "2026-09")

        self.assertEqual(client.get_anomaly_feedback()[0]["period"], "2026-09")

    def test_upserting_nothing_is_a_no_op(self):
        self.assertEqual(self.client().upsert_anomalies([]), 0)


class OutlierShimTests(PostgresBackedTestCase):
    """`set_outlier_flags` keeps the React outliers view populated. It clears the previous run's flags before setting the new ones, so
    both halves need checking against real rows."""

    def setUp(self):
        super().setUp()
        self.seed_account()
        self.seed_transaction("h1", "2026-09-01", "ONE", -10.0)
        self.seed_transaction("h2", "2026-09-02", "TWO", -20.0)
        self.seed_transaction("h3", "2026-09-03", "THREE", -30.0)

    def _flagged(self):
        rows = self.execute(
            "SELECT transaction_hash FROM transactions WHERE is_outlier ORDER BY transaction_hash"
        )
        return [r[0] for r in rows]

    def test_flags_exactly_the_hashes_given(self):
        self.assertEqual(self.client().set_outlier_flags(["h1", "h3"]), 2)
        self.assertEqual(self._flagged(), ["h1", "h3"])

    def test_a_later_run_clears_the_previous_flags(self):
        client = self.client()
        client.set_outlier_flags(["h1", "h3"])
        client.set_outlier_flags(["h2"])

        self.assertEqual(self._flagged(), ["h2"])

    def test_an_empty_list_clears_everything(self):
        client = self.client()
        client.set_outlier_flags(["h1"])

        self.assertEqual(client.set_outlier_flags([]), 0)
        self.assertEqual(self._flagged(), [])

    def test_unknown_hashes_flag_nothing(self):
        self.assertEqual(self.client().set_outlier_flags(["nope"]), 0)


if __name__ == "__main__":
    unittest.main()
