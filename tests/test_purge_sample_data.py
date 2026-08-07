from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from scripts.purge_sample_data import main


class MainTests(unittest.TestCase):
    def _settings(self) -> MagicMock:
        return MagicMock(database_url="postgresql://prod")

    def test_no_sample_data_is_a_noop(self) -> None:
        db_instance = MagicMock()
        db_instance.accounts_for_source.return_value = []
        with (
            patch("scripts.purge_sample_data.load_settings") as load_settings,
            patch("scripts.purge_sample_data.DatabaseClient", return_value=db_instance),
            patch("sys.argv", ["purge_sample_data.py"]),
        ):
            load_settings.return_value = self._settings()
            exit_code = main()

        self.assertEqual(exit_code, 0)
        db_instance.purge_source.assert_not_called()

    def test_dry_run_issues_no_delete(self) -> None:
        db_instance = MagicMock()
        db_instance.accounts_for_source.return_value = [
            {"account_key": "sample:Alex Chequing", "account_name": "Alex Chequing", "transaction_count": 10}
        ]
        db_instance.count_by_source.return_value = {
            "sample": {"accounts": 1, "transactions": 10},
            "plaid": {"accounts": 3, "transactions": 500},
        }
        with (
            patch("scripts.purge_sample_data.load_settings") as load_settings,
            patch("scripts.purge_sample_data.DatabaseClient", return_value=db_instance),
            patch("sys.argv", ["purge_sample_data.py"]),
        ):
            load_settings.return_value = self._settings()
            exit_code = main()

        self.assertEqual(exit_code, 0)
        db_instance.purge_source.assert_not_called()

    def test_apply_calls_purge_source(self) -> None:
        db_instance = MagicMock()
        db_instance.accounts_for_source.return_value = [
            {"account_key": "sample:Alex Chequing", "account_name": "Alex Chequing", "transaction_count": 10}
        ]
        db_instance.count_by_source.return_value = {
            "sample": {"accounts": 1, "transactions": 10},
            "plaid": {"accounts": 3, "transactions": 500},
        }
        db_instance.purge_source.return_value = (10, 1)
        with (
            patch("scripts.purge_sample_data.load_settings") as load_settings,
            patch("scripts.purge_sample_data.DatabaseClient", return_value=db_instance),
            patch("sys.argv", ["purge_sample_data.py", "--apply"]),
        ):
            load_settings.return_value = self._settings()
            exit_code = main()

        self.assertEqual(exit_code, 0)
        db_instance.purge_source.assert_called_once_with("sample")


if __name__ == "__main__":
    unittest.main()
