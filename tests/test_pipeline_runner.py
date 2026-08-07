from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import psycopg

from core.config import ConfigError
from pipeline.runner import _build_ingestor, main, run_pipeline


def _settings(**overrides) -> SimpleNamespace:
    base = dict(
        database_url="postgresql://x",
        plaid_client_id="client-id",
        plaid_secret="secret",
        plaid_access_tokens=["token-1", "token-2"],
        plaid_access_token_owners=["Alex", "Sam"],
        plaid_base_url="https://sandbox.plaid.com",
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
    def _transactions_frame(self) -> pd.DataFrame:
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
                }
            ]
        )

    def test_happy_path(self) -> None:
        settings = _settings()
        database = MagicMock()
        database.canonicalize_account_keys.return_value = {}
        database.upsert_transactions.return_value = (1, 0)

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = [{"account_key": "plaid:acc1"}]
        ingestor.fetch_transactions.return_value = self._transactions_frame()

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

    def test_empty_frame(self) -> None:
        settings = _settings()
        database = MagicMock()
        database.canonicalize_account_keys.return_value = {}

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = []
        ingestor.fetch_transactions.return_value = pd.DataFrame(
            columns=[
                "transaction_id",
                "date",
                "description",
                "amount",
                "balance",
                "account_key",
                "account_name",
                "source",
            ]
        )

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            result = run_pipeline()

        database.upsert_categories.assert_not_called()
        database.upsert_transactions.assert_not_called()
        self.assertTrue(result.transactions.empty)
        self.assertEqual(result.inserted, 0)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.removed, 0)

    def test_calls_upsert_plaid_accounts(self) -> None:
        settings = _settings()
        database = MagicMock()
        database.canonicalize_account_keys.return_value = {}
        database.upsert_transactions.return_value = (1, 0)

        accounts = [{"account_key": "plaid:acc1", "account_name": "Checking"}]
        owner_by_token = dict(
            zip(settings.plaid_access_tokens, settings.plaid_access_token_owners, strict=True)
        )

        ingestor = MagicMock()
        ingestor.fetch_accounts.return_value = accounts
        ingestor.fetch_transactions.return_value = self._transactions_frame()

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.PlaidIngestor", return_value=ingestor),
            patch("pipeline.runner.DatabaseClient", return_value=database),
        ):
            run_pipeline()

        ingestor.fetch_accounts.assert_called_once_with(owner_by_token)
        database.upsert_plaid_accounts.assert_called_once_with(accounts)


class MainTests(unittest.TestCase):
    def test_success_logs_run_with_counts(self) -> None:
        settings = _settings()
        database = MagicMock()
        result = SimpleNamespace(transactions=pd.DataFrame(), inserted=3, updated=1, removed=2)

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
        args = database.log_pipeline_run.call_args[0]
        self.assertEqual(args[1], "success")

    def test_operational_error_logs_failure_without_message(self) -> None:
        settings = _settings()
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
        self.assertNotIn("error_message", kwargs)

    def test_generic_exception_logs_failure_with_message(self) -> None:
        settings = _settings()
        database = MagicMock()

        with (
            patch("pipeline.runner.load_settings", return_value=settings),
            patch("pipeline.runner.DatabaseClient", return_value=database),
            patch("pipeline.runner.run_pipeline", side_effect=RuntimeError("boom")),
        ):
            with self.assertRaises(RuntimeError):
                main()

        database.log_pipeline_run.assert_called_once()
        args, kwargs = database.log_pipeline_run.call_args
        self.assertEqual(args[1], "failed")
        self.assertEqual(kwargs["error_class"], "RuntimeError")
        self.assertEqual(kwargs["error_message"], "boom")

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
