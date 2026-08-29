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
) -> SyncResult:
    return SyncResult(
        added=added if added is not None else _empty_frame(),
        modified=modified if modified is not None else _empty_frame(),
        removed_ids=removed_ids or [],
        duplicate_accounts_skipped=duplicate_accounts_skipped,
        full_refresh=full_refresh,
        cursors=cursors or {},
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
        ingestor.fetch_accounts.return_value = [{"account_key": "plaid:acc1"}]
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = accounts
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
        ingestor.fetch_accounts.return_value = accounts
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
        ingestor.fetch_accounts.return_value = []
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
        ingestor.fetch_accounts.return_value = []
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


if __name__ == "__main__":
    unittest.main()
