from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import requests

from ingestion.plaid_ingestor import PlaidIngestor


def _ingestor() -> PlaidIngestor:
    return PlaidIngestor(client_id="cid", secret="secret", access_tokens=["token-123456"])


class PostErrorLoggingTests(unittest.TestCase):
    def test_json_error_body_logs_only_status_and_error_fields(self) -> None:
        response = MagicMock()
        response.ok = False
        response.status_code = 400
        response.json.return_value = {
            "error_type": "INVALID_REQUEST",
            "error_code": "INVALID_FIELD",
            "error_message": "account_id abc123 for user Alex is invalid",
            "request_id": "req-1",
        }
        response.raise_for_status.side_effect = requests.HTTPError("http error")

        with (
            patch("ingestion.plaid_ingestor.requests.post", return_value=response),
            patch("ingestion.plaid_ingestor.LOGGER") as logger,
        ):
            with self.assertRaises(requests.HTTPError):
                _ingestor()._post("transactions/get", {})

        logger.error.assert_called_once()
        args = logger.error.call_args[0]
        self.assertNotIn("account_id abc123", " ".join(str(a) for a in args))
        self.assertIn("status=%s error_type=%s error_code=%s", args[0])
        self.assertEqual(args[1:], (400, "INVALID_REQUEST", "INVALID_FIELD"))
        response.json.assert_called()  # only .json() was used, never .text

    def test_non_json_body_logs_status_only(self) -> None:
        response = MagicMock()
        response.ok = False
        response.status_code = 502
        response.json.side_effect = ValueError("not json")
        response.raise_for_status.side_effect = requests.HTTPError("http error")

        with (
            patch("ingestion.plaid_ingestor.requests.post", return_value=response),
            patch("ingestion.plaid_ingestor.LOGGER") as logger,
        ):
            with self.assertRaises(requests.HTTPError):
                _ingestor()._post("transactions/get", {})

        logger.error.assert_called_once()
        args = logger.error.call_args[0]
        self.assertIn("status=%s (non-JSON body)", args[0])
        self.assertEqual(args[1], 502)


class DuplicateAccountSkipCountTests(unittest.TestCase):
    def test_skip_is_counted_not_logged(self) -> None:
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=["tok-a", "tok-b"])

        account_a = {
            "account_key": "plaid:acc-a",
            "account_name": "Checking (••••1234)",
            "official_name": "Chequing",
            "account_type": "depository",
            "account_subtype": "checking",
            "mask": "1234",
            "_account_id": "acc-a",
        }
        account_b = dict(account_a, account_key="plaid:acc-b", _account_id="acc-b")

        with (
            patch.object(ingestor, "_fetch_accounts_raw", side_effect=[[account_a], [account_b]]),
            patch.object(
                ingestor, "_request_page", return_value={"transactions": [], "total_transactions": 0}
            ),
            patch("ingestion.plaid_ingestor.LOGGER") as logger,
        ):
            result = ingestor.fetch_transactions(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))

        self.assertEqual(result.duplicate_accounts_skipped, 1)
        logger.info.assert_not_called()


class RequestFailureLoggingTests(unittest.TestCase):
    def test_fetch_accounts_logs_class_name_only_no_traceback(self) -> None:
        ingestor = _ingestor()

        with (
            patch.object(ingestor, "_fetch_accounts_raw", side_effect=requests.ConnectionError("boom")),
            patch("ingestion.plaid_ingestor.LOGGER") as logger,
        ):
            with self.assertRaises(requests.ConnectionError):
                ingestor.fetch_accounts({})

        logger.error.assert_called_once()
        logger.exception.assert_not_called()
        args = logger.error.call_args[0]
        self.assertEqual(args[1:], ("123456", "ConnectionError"))

    def test_fetch_transactions_page_request_logs_class_name_only_no_traceback(self) -> None:
        ingestor = _ingestor()

        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_page", side_effect=requests.Timeout("boom")),
            patch("ingestion.plaid_ingestor.LOGGER") as logger,
        ):
            with self.assertRaises(requests.Timeout):
                ingestor.fetch_transactions(start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))

        logger.error.assert_called_once()
        logger.exception.assert_not_called()
        args = logger.error.call_args[0]
        self.assertEqual(args[1:], ("123456", "Timeout"))


if __name__ == "__main__":
    unittest.main()
