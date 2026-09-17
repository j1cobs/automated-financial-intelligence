from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import psycopg

from core.config import ConfigError
from ingestion.plaid_ingestor import SyncResult
from pipeline.runner import _build_ingestor, main, run_pipeline

_NORMALIZED_COLUMNS = [
    "transaction_id",
    "date",
    "description",
    "amount",
    "balance",
    "account_key",
    "account_name",
    "source",
    "pending",
    "pending_transaction_id",
]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_NORMALIZED_COLUMNS)


def _sync_result(
    added: pd.DataFrame | None = None,
    modified: pd.DataFrame | None = None,
    removed_ids: list[str] | None = None,
    duplicate_accounts_skipped: int = 0,
    full_refresh: bool = True,
    cursors: dict[str, str] | None = None,
    failed_tokens: dict[str, str] | None = None,
) -> SyncResult:
    return SyncResult(
        added=added if added is not None else _empty_frame(),
        modified=modified if modified is not None else _empty_frame(),
        removed_ids=removed_ids or [],
        duplicate_accounts_skipped=duplicate_accounts_skipped,
        full_refresh=full_refresh,
        cursors=cursors or {},
        failed_tokens=failed_tokens or {},
    )


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        database_url="postgresql://x",
        plaid_client_id="client-id",
        plaid_secret="secret",
        plaid_access_tokens=["token-1", "token-2"],
        plaid_access_token_owners=["Alex", "Sam"],
        plaid_base_url="https://sandbox.plaid.com",
        github_event_name=None,
        categorizer_mode="cascade",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class BuildIngestorTests(unittest.TestCase):
    def test_returns_plaid(self) -> None:
        settings = _settings()
        with patch("pipeline.runner.PlaidIngestor") as plaid_ingestor:
            result = _build_ingestor(settings)

        plaid_ingestor.assert_called_once_with(
            client_id="client-id",
            secret="secret",
            access_tokens=["token-1", "token-2"],
            base_url="https://sandbox.plaid.com",
        )
        self.assertEqual(result, plaid_ingestor.return_value)

    def test_missing_client_id(self) -> None:
        settings = _settings(plaid_client_id=None)
        with self.assertRaises(ConfigError):
            _build_ingestor(settings)

    def test_missing_secret(self) -> None:
        settings = _settings(plaid_secret=None)
        with self.assertRaises(ConfigError):
            _build_ingestor(settings)

    def test_empty_tokens(self) -> None:
        settings = _settings(plaid_access_tokens=[])
        with self.assertRaises(ConfigError):
            _build_ingestor(settings)

    def test_owner_token_mismatch(self) -> None:
        settings = _settings(
            plaid_access_tokens=["token-1", "token-2"],
            plaid_access_token_owners=["Alex"],
        )
        with self.assertRaises(ConfigError):
            _build_ingestor(settings)


class RunPipelineTests(unittest.TestCase):
    def _added_frame(self) -> pd.DataFrame:
        return pd.DataFrame.from_records(
            [
                {
                    "transaction_id": "tx-1",
                    "date": "2026-07-01",
                    "description": "Coffee Shop",
                    "amount": 5.25,
                    "balance": None,
                    "account_key": "plaid:acc1",
                    "account_name": "Checking",
                    "source": "plaid",
                    "pending": False,
                    "pending_transaction_id": None,
                }
            ]
        )

    def _added_frame_with_fingerprint(self, fingerprint: str) -> pd.DataFrame:
        """Create a transaction frame with _token_fingerprint for testing token filtering."""
        return pd.DataFrame.from_records(
            [
                {
                    "transaction_id": f"tx-{fingerprint[:8]}",
                    "date": "2026-07-01",
                    "description": "Coffee Shop",
                    "amount": 5.25,
                    "balance": None,
                    "account_key": f"plaid:acc-{fingerprint[:8]}",
                    "account_name": "Checking",
                    "source": "plaid",
                    "pending": False,
                    "pending_transaction_id": None,
                    "_token_fingerprint": fingerprint,
                }
            ]
        )

    def _database(self) -> MagicMock:
        database = MagicMock()
        database.canonicalize_account_keys.return_value = {}
        database.upsert_transactions.return_value = (0, 0)
        database.delete_transactions_by_external_ids.return_value = 0
        database.reconcile_transactions.return_value = 0
        database.get_sync_cursors.return_value = {}
        database.get_all_merchant_categories.return_value = {}
        return database

    def test_happy_path(self) -> None:
        settings = _settings()
        database = self._database()
        database.upsert_transactions.return_value = (1, 0)

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([{"account_key": "plaid:acc1"}], {})
        ingestor.sync_transactions.return_value = _sync_result(
            added=self._added_frame(), duplicate_accounts_skipped=2, full_refresh=True
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        database.upsert_categories.assert_called_once()
        database.upsert_transactions.assert_called_once()
        self.assertIn("category", result.transactions.columns)
        self.assertIn("is_outlier", result.transactions.columns)
        self.assertTrue(all(isinstance(value, str) for value in result.transactions["category"]))
        self.assertTrue(all(isinstance(value, (bool,)) for value in result.transactions["is_outlier"]))
        self.assertEqual(result.inserted, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.duplicate_accounts_skipped, 2)

    def test_empty_sync_delta_does_not_crash_and_still_persists_cursor(self) -> None:
        """Even a no-change /transactions/sync response returns a fresh next_cursor that
        must be saved -- otherwise the next run re-fetches the same empty window forever."""
        settings = _settings()
        database = self._database()

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(
            full_refresh=False, cursors={"fp-1": "cursor-after-empty-delta"}
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        self.assertTrue(result.transactions.empty)
        self.assertEqual(result.inserted, 0)
        self.assertEqual(result.updated, 0)
        database.set_sync_cursor.assert_called_once_with("fp-1", "cursor-after-empty-delta")

    def test_empty_sync_with_full_refresh_calls_reconcile_and_completes(self) -> None:
        """Regression test: when both added and modified are empty but full_refresh=True,
        reconcile_transactions should still be called and the pipeline should complete without
        raising."""
        settings = _settings()
        database = self._database()
        database.reconcile_transactions.return_value = 0

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(full_refresh=True)

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        self.assertTrue(result.transactions.empty)
        self.assertEqual(result.inserted, 0)
        self.assertEqual(result.updated, 0)
        database.reconcile_transactions.assert_called_once()
        _, kwargs = database.reconcile_transactions.call_args
        self.assertEqual(kwargs["full_refresh"], True)

    def test_reconcile_not_called_when_sync_is_not_a_full_refresh(self) -> None:
        settings = _settings()
        database = self._database()

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(added=self._added_frame(), full_refresh=False)

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        database.reconcile_transactions.assert_not_called()
        self.assertEqual(result.removed, 0)
        self.assertFalse(result.full_refresh)

    def test_reconcile_called_with_full_refresh_true_when_sync_is_a_full_refresh(self) -> None:
        settings = _settings()
        database = self._database()
        database.reconcile_transactions.return_value = 3

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(added=self._added_frame(), full_refresh=True)

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        database.reconcile_transactions.assert_called_once()
        _, kwargs = database.reconcile_transactions.call_args
        self.assertEqual(kwargs["full_refresh"], True)
        self.assertEqual(result.removed, 3)

    def test_cursor_not_persisted_when_upsert_raises(self) -> None:
        """Proves the ordering is real, not just visually last in the source: if the cursor
        were advanced before the write commits, a crash here would lose that delta for good,
        since sync never replays a delta once its cursor is passed."""
        settings = _settings()
        database = self._database()
        database.upsert_transactions.side_effect = RuntimeError("write failed")

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(
            added=self._added_frame(), cursors={"fp-1": "cursor-should-not-be-saved"}
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            with self.assertRaises(RuntimeError):
                run_pipeline()

        database.set_sync_cursor.assert_not_called()

    def test_cursor_not_persisted_when_delete_by_external_ids_raises(self) -> None:
        settings = _settings()
        database = self._database()
        database.delete_transactions_by_external_ids.side_effect = RuntimeError("delete failed")

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(
            added=self._added_frame(),
            removed_ids=["removed-1"],
            cursors={"fp-1": "cursor-should-not-be-saved"},
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            with self.assertRaises(RuntimeError):
                run_pipeline()

        database.set_sync_cursor.assert_not_called()

    def test_calls_upsert_plaid_accounts(self) -> None:
        settings = _settings()
        database = self._database()
        database.upsert_transactions.return_value = (1, 0)

        accounts = [{"account_key": "plaid:acc1", "account_name": "Checking"}]
        owner_by_token = dict(
            zip(settings.plaid_access_tokens, settings.plaid_access_token_owners, strict=True)
        )

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = (accounts, {})
        ingestor.sync_transactions.return_value = _sync_result(added=self._added_frame())

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            run_pipeline()

        ingestor.fetch_accounts.assert_called_once_with(owner_by_token)
        database.upsert_plaid_accounts.assert_called_once_with(accounts)

    def test_records_balance_snapshots_after_upserting_accounts(self) -> None:
        settings = _settings()
        database = self._database()
        database.upsert_transactions.return_value = (1, 0)

        accounts = [{"account_key": "plaid:acc1", "account_name": "Checking", "balance_current": 200.0}]

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = (accounts, {})
        ingestor.sync_transactions.return_value = _sync_result(added=self._added_frame())

        call_order: list[str] = []
        database.upsert_plaid_accounts.side_effect = lambda *_: call_order.append("upsert_plaid_accounts")
        database.record_balance_snapshots.side_effect = lambda *_: call_order.append(
            "record_balance_snapshots"
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            run_pipeline()

        database.record_balance_snapshots.assert_called_once_with(accounts)
        self.assertEqual(call_order, ["upsert_plaid_accounts", "record_balance_snapshots"])

    def test_cross_step_exclusion_token_a_sync_succeeds_accounts_fails(self) -> None:
        """Cross-step exclusion scenario: Token A syncs successfully (produces transactions)
        but fails during fetch_accounts. Token B succeeds at both steps.

        Expected behavior:
        - Only B's account is upserted (A's account filtered out)
        - Only B's transactions are persisted (A's transactions filtered out)
        - Only B's cursor is advanced (A's cursor skipped)
        - Status is "partial_success"
        - failed_accounts_summary is non-None and mentions token A
        """
        settings = _settings()
        database = self._database()
        database.upsert_transactions.return_value = (1, 0)

        # Token A fingerprint and B fingerprint (SHA256 hashes of the tokens)
        import hashlib
        fp_a = hashlib.sha256("token-1".encode()).hexdigest()
        fp_b = hashlib.sha256("token-2".encode()).hexdigest()

        # Token A: sync succeeds (produces transactions) but fetch_accounts fails
        # Token B: both succeed
        accounts_b = [{"account_key": f"plaid:acc-{fp_b[:8]}", "account_name": "B Checking", "_token_fingerprint": fp_b}]
        accounts_failed = {fp_a: "Item error: NO_ACCOUNTS"}

        added_a = self._added_frame_with_fingerprint(fp_a)
        added_b = self._added_frame_with_fingerprint(fp_b)
        combined_added = pd.concat([added_a, added_b], ignore_index=True)

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = (accounts_b, accounts_failed)
        ingestor.sync_transactions.return_value = _sync_result(
            added=combined_added,
            cursors={fp_a: "cursor-a", fp_b: "cursor-b"},
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        # Assert only B's account is upserted
        database.upsert_plaid_accounts.assert_called_once()
        upserted_accounts = database.upsert_plaid_accounts.call_args[0][0]
        self.assertEqual(len(upserted_accounts), 1)
        self.assertEqual(upserted_accounts[0]["account_key"], f"plaid:acc-{fp_b[:8]}")
        # Verify _token_fingerprint was stripped
        self.assertNotIn("_token_fingerprint", upserted_accounts[0])

        # Assert only B's transactions are persisted
        database.upsert_transactions.assert_called_once()
        upserted_transactions = database.upsert_transactions.call_args[0][0]
        self.assertEqual(len(upserted_transactions), 1)
        self.assertEqual(upserted_transactions.iloc[0]["account_key"], f"plaid:acc-{fp_b[:8]}")

        # Assert only B's cursor is advanced
        self.assertEqual(database.set_sync_cursor.call_count, 1)
        cursor_call = database.set_sync_cursor.call_args[0]
        self.assertEqual(cursor_call[0], fp_b)
        self.assertEqual(cursor_call[1], "cursor-b")

        # Assert status is partial_success
        self.assertEqual(result.status, "partial_success")

        # Assert failed_accounts_summary is not None and contains A's info
        self.assertIsNotNone(result.failed_accounts_summary)
        self.assertIn("Alex", result.failed_accounts_summary)  # Token A owner name
        self.assertIn("1/2", result.failed_accounts_summary)  # 1 of 2 failed

    def test_all_tokens_fail(self) -> None:
        """When all configured tokens fail (both sync and/or account fetch),
        status should be "failed"."""
        import hashlib

        settings = _settings()
        database = self._database()

        fp_a = hashlib.sha256("token-1".encode()).hexdigest()
        fp_b = hashlib.sha256("token-2".encode()).hexdigest()

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {fp_a: "NO_ACCOUNTS", fp_b: "INVALID_REQUEST"})
        ingestor.sync_transactions.return_value = _sync_result(
            failed_tokens={fp_a: "ITEM_LOGIN_REQUIRED"}
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        self.assertEqual(result.status, "failed")
        self.assertIsNotNone(result.failed_accounts_summary)
        self.assertIn("2/2", result.failed_accounts_summary)

    def test_all_tokens_succeed_returns_success_status(self) -> None:
        """Smoke test: when no tokens fail, status should be "success"
        and failed_accounts_summary should be None."""
        import hashlib

        settings = _settings()
        database = self._database()
        database.upsert_transactions.return_value = (1, 0)

        fp_a = hashlib.sha256("token-1".encode()).hexdigest()
        fp_b = hashlib.sha256("token-2".encode()).hexdigest()

        accounts = [
            {"account_key": f"plaid:acc-{fp_a[:8]}", "_token_fingerprint": fp_a},
            {"account_key": f"plaid:acc-{fp_b[:8]}", "_token_fingerprint": fp_b},
        ]

        added = pd.concat(
            [
                self._added_frame_with_fingerprint(fp_a),
                self._added_frame_with_fingerprint(fp_b),
            ],
            ignore_index=True,
        )

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = (accounts, {})
        ingestor.sync_transactions.return_value = _sync_result(
            added=added,
            cursors={fp_a: "cursor-a", fp_b: "cursor-b"},
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        self.assertEqual(result.status, "success")
        self.assertIsNone(result.failed_accounts_summary)
        # All cursors should be advanced
        self.assertEqual(database.set_sync_cursor.call_count, 2)


class CategorizerModeWiringTests(unittest.TestCase):
    """categorizer_mode selects between the cascade (whole-frame) and placeholder
    (description-Series) call shapes -- see analytics/models.py::build_models and
    PLAN.md's Step 3-wiring."""

    def _added_frame(self) -> pd.DataFrame:
        return pd.DataFrame.from_records(
            [
                {
                    "transaction_id": "tx-1",
                    "date": "2026-07-01",
                    "description": "Coffee Shop",
                    "amount": 5.25,
                    "balance": None,
                    "account_key": "plaid:acc1",
                    "account_name": "Checking",
                    "source": "plaid",
                    "pending": False,
                    "pending_transaction_id": None,
                    "merchant_name": "Coffee Shop",
                    "pfc_primary": "FOOD_AND_DRINK",
                    "pfc_detailed": "FOOD_AND_DRINK_COFFEE",
                    "pfc_confidence": "HIGH",
                }
            ]
        )

    def _database(self) -> MagicMock:
        database = MagicMock()
        database.canonicalize_account_keys.return_value = {}
        database.upsert_transactions.return_value = (1, 0)
        database.delete_transactions_by_external_ids.return_value = 0
        database.reconcile_transactions.return_value = 0
        database.get_sync_cursors.return_value = {}
        return database

    def test_cascade_mode_calls_merchant_lookup_and_passes_whole_frame(self) -> None:
        settings = _settings(categorizer_mode="cascade")
        database = self._database()
        database.get_all_merchant_categories.return_value = {"COFFEE SHOP": "FOOD_AND_DRINK"}

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(added=self._added_frame())

        fake_bundle = SimpleNamespace(
            classifier=MagicMock(),
            outlier_detector=MagicMock(),
        )
        fake_bundle.classifier.categorize.return_value = self._added_frame().assign(
            category="FOOD_AND_DRINK", category_source="merchant"
        )
        fake_bundle.outlier_detector.score.side_effect = lambda frame: frame.assign(
            outlier_score=0.0, is_outlier=False
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.build_models", return_value=fake_bundle) as build_models,
        ):
            run_pipeline()

        build_models.assert_called_once_with("cascade")
        database.get_all_merchant_categories.assert_called_once()
        fake_bundle.classifier.categorize.assert_called_once()
        call_args = fake_bundle.classifier.categorize.call_args[0]
        frame_arg, lookup_arg = call_args[0], call_args[1]
        # The whole frame, not just a description Series -- pfc_primary/merchant_name
        # must survive into the call.
        self.assertIsInstance(frame_arg, pd.DataFrame)
        self.assertIn("pfc_primary", frame_arg.columns)
        self.assertIn("merchant_name", frame_arg.columns)
        self.assertEqual(lookup_arg, {"COFFEE SHOP": "FOOD_AND_DRINK"})

    def test_placeholder_mode_still_uses_series_in_series_out(self) -> None:
        settings = _settings(categorizer_mode="placeholder")
        database = self._database()

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = ([], {})
        ingestor.sync_transactions.return_value = _sync_result(added=self._added_frame())

        fake_bundle = SimpleNamespace(
            classifier=MagicMock(),
            outlier_detector=MagicMock(),
        )
        fake_bundle.classifier.categorize.return_value = pd.Series(["Uncategorized"])
        fake_bundle.outlier_detector.score.side_effect = lambda frame: frame.assign(
            outlier_score=0.0, is_outlier=False
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.build_models", return_value=fake_bundle) as build_models,
        ):
            result = run_pipeline()

        build_models.assert_called_once_with("placeholder")
        database.get_all_merchant_categories.assert_not_called()
        fake_bundle.classifier.categorize.assert_called_once()
        call_args = fake_bundle.classifier.categorize.call_args[0]
        self.assertIsInstance(call_args[0], pd.Series)
        self.assertEqual(list(result.transactions["category"]), ["Uncategorized"])


class MainTests(unittest.TestCase):
    def test_success_logs_run_with_counts(self) -> None:
        settings = _settings(github_event_name="workflow_dispatch")
        database = MagicMock()
        result = SimpleNamespace(
            transactions=pd.DataFrame(),
            inserted=3,
            updated=1,
            removed=2,
            duplicate_accounts_skipped=4,
            removed_count=5,
            full_refresh=True,
            status="success",
            failed_accounts_summary=None,
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.run_pipeline", return_value=result),
        ):
            main()

        database.log_pipeline_run.assert_called_once()
        _, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(kwargs["transactions_inserted"], 3)
        self.assertEqual(kwargs["transactions_updated"], 1)
        self.assertEqual(kwargs["stale_duplicates_removed"], 2)
        self.assertEqual(kwargs["duplicate_accounts_skipped"], 4)
        self.assertEqual(kwargs["removed_count"], 5)
        self.assertEqual(kwargs["full_refresh"], True)
        self.assertEqual(kwargs["trigger_type"], "workflow_dispatch")
        args = database.log_pipeline_run.call_args[0]
        self.assertEqual(args[1], "success")

    def test_success_defaults_trigger_type_to_local(self) -> None:
        settings = _settings()  # github_event_name defaults to None
        database = MagicMock()
        result = SimpleNamespace(
            transactions=pd.DataFrame(),
            inserted=0,
            updated=0,
            removed=0,
            duplicate_accounts_skipped=0,
            removed_count=0,
            full_refresh=False,
            status="success",
            failed_accounts_summary=None,
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.run_pipeline", return_value=result),
        ):
            main()

        _, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(kwargs["trigger_type"], "local")

    def test_operational_error_logs_failure_without_message(self) -> None:
        settings = _settings(github_event_name="schedule")
        database = MagicMock()

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch(
                "pipeline.runner.run_pipeline",
                side_effect=psycopg.OperationalError("connection refused"),
            ),
        ):
            with self.assertRaises(SystemExit):
                main()

        database.log_pipeline_run.assert_called_once()
        args, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(args[1], "failed")
        self.assertEqual(kwargs["error_class"], "OperationalError")
        self.assertEqual(kwargs["trigger_type"], "schedule")
        self.assertNotIn("error_message", kwargs)

    def test_generic_exception_logs_failure_with_message(self) -> None:
        settings = _settings(github_event_name="schedule")
        database = MagicMock()

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.run_pipeline", side_effect=RuntimeError("boom")),
            patch("pipeline.runner.LOGGER") as logger,
        ):
            with self.assertRaises(RuntimeError):
                main()

        database.log_pipeline_run.assert_called_once()
        args, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(args[1], "failed")
        self.assertEqual(kwargs["error_class"], "RuntimeError")
        self.assertEqual(kwargs["error_message"], "boom")
        self.assertEqual(kwargs["trigger_type"], "schedule")

        logger.exception.assert_not_called()
        logger.error.assert_called_once()
        error_args = logger.error.call_args[0]
        self.assertEqual(error_args[1:], ("RuntimeError",))

    def test_config_error_before_database_construction_skips_logging(self) -> None:
        database_class = MagicMock()

        with (
            patch("pipeline.runner.load_settings", side_effect=ConfigError("DATABASE_URL is required")),
            patch("pipeline.runner.DatabaseClient", database_class),
        ):
            with self.assertRaises(ConfigError):
                main()

        database_class.assert_not_called()

    def test_partial_success_logs_run_with_failed_accounts_summary(self) -> None:
        """When some tokens fail, status is 'partial_success', logs with error_message."""
        settings = _settings(github_event_name="schedule")
        database = MagicMock()
        result = SimpleNamespace(
            transactions=pd.DataFrame(),
            inserted=1,
            updated=0,
            removed=0,
            duplicate_accounts_skipped=0,
            removed_count=0,
            full_refresh=False,
            status="partial_success",
            failed_accounts_summary="1/2 accounts failed: Alex (NO_ACCOUNTS)",
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.run_pipeline", return_value=result),
        ):
            with self.assertRaises(SystemExit) as context:
                main()

        self.assertEqual(context.exception.code, 1)
        database.log_pipeline_run.assert_called_once()
        args, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(args[1], "partial_success")
        self.assertEqual(kwargs["error_message"], "1/2 accounts failed: Alex (NO_ACCOUNTS)")
        self.assertEqual(kwargs["transactions_inserted"], 1)

    def test_failed_status_logs_run_with_failed_accounts_summary(self) -> None:
        """When all tokens fail, status is 'failed', logs with error_message."""
        settings = _settings(github_event_name="local")
        database = MagicMock()
        result = SimpleNamespace(
            transactions=pd.DataFrame(),
            inserted=0,
            updated=0,
            removed=0,
            duplicate_accounts_skipped=0,
            removed_count=0,
            full_refresh=False,
            status="failed",
            failed_accounts_summary="2/2 accounts failed: Alex (NO_ACCOUNTS); Sam (INVALID_REQUEST)",
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.run_pipeline", return_value=result),
        ):
            with self.assertRaises(SystemExit) as context:
                main()

        self.assertEqual(context.exception.code, 1)
        database.log_pipeline_run.assert_called_once()
        args, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(args[1], "failed")
        self.assertEqual(
            kwargs["error_message"],
            "2/2 accounts failed: Alex (NO_ACCOUNTS); Sam (INVALID_REQUEST)",
        )
        self.assertNotIn("transactions_inserted", kwargs)


if __name__ == "__main__":
    unittest.main()
