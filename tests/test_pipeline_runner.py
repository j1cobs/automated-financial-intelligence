from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

from core.config import ConfigError
from pipeline.runner import _build_ingestor, run_pipeline


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
        self.assertIn("category", result.columns)
        self.assertIn("is_outlier", result.columns)
        self.assertTrue(all(isinstance(value, str) for value in result["category"]))
        self.assertTrue(all(isinstance(value, (bool,)) for value in result["is_outlier"]))

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
        self.assertTrue(result.empty)

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


if __name__ == "__main__":
    unittest.main()
