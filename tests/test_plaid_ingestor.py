from __future__ import annotations

import hashlib
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import requests

from ingestion.plaid_ingestor import PlaidIngestor


def _ingestor() -> PlaidIngestor:
    return PlaidIngestor(client_id="cid", secret="secret", access_tokens=["token-123456"])


def _sync_page(added=None, modified=None, removed=None, has_more=False, next_cursor="cursor-1") -> dict:
    return {
        "added": added or [],
        "modified": modified or [],
        "removed": removed or [],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


def _http_error(error_code: str) -> requests.HTTPError:
    response = MagicMock()
    response.json.return_value = {"error_code": error_code}
    error = requests.HTTPError("plaid sync error")
    error.response = response
    return error


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
        fingerprint = hashlib.sha256(b"token-123456").hexdigest()

        with (
            patch.object(ingestor, "_fetch_accounts_raw", side_effect=requests.ConnectionError("boom")),
            patch("ingestion.plaid_ingestor.LOGGER") as logger,
        ):
            accounts, failed_tokens = ingestor.fetch_accounts({})

        # Per-token isolation: fetch_accounts catches the error and returns it in failed_tokens
        self.assertEqual(accounts, [])
        self.assertEqual(failed_tokens, {fingerprint: "ConnectionError"})
        logger.warning.assert_called_once()
        logger.exception.assert_not_called()
        args = logger.warning.call_args[0]
        self.assertIn("Failed to fetch accounts", args[0])
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


class SyncFullRefreshTests(unittest.TestCase):
    def test_full_refresh_true_when_every_cursor_absent(self) -> None:
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=["tok-a", "tok-b"])
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_sync_page", return_value=_sync_page()),
        ):
            result = ingestor.sync_transactions({})
        self.assertTrue(result.full_refresh)

    def test_full_refresh_false_when_any_stored_cursor_present(self) -> None:
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=["tok-a", "tok-b"])
        fp_a = hashlib.sha256(b"tok-a").hexdigest()
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_sync_page", return_value=_sync_page()),
        ):
            result = ingestor.sync_transactions({fp_a: "existing-cursor"})
        self.assertFalse(result.full_refresh)


class SyncRemovedIdsTests(unittest.TestCase):
    def test_removed_ids_include_pending_transaction_id_not_in_removed_array(self) -> None:
        """The core Le Germain bug fix (Phase 17): a cold-start sync has no prior baseline for
        `removed` to reference, so Plaid's only way to state that a pending authorization was
        superseded is the `pending_transaction_id` carried on the settled row. removed_ids must
        pick that up even though Plaid's `removed` array itself is empty."""
        ingestor = _ingestor()
        settled = {
            "transaction_id": "settled-723",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "name": "Le Germain Hotel",
            "amount": 723.01,
            "pending": False,
            "pending_transaction_id": "stale-authorization-id",
        }
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(
                ingestor,
                "_request_sync_page",
                return_value=_sync_page(added=[settled], removed=[]),
            ),
        ):
            result = ingestor.sync_transactions({})

        self.assertEqual(result.removed_ids, ["stale-authorization-id"])

    def test_removed_ids_is_union_of_removed_array_and_pending_transaction_ids(self) -> None:
        ingestor = _ingestor()
        added = {
            "transaction_id": "settled-1",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "name": "Merchant",
            "amount": 10.0,
            "pending": False,
            "pending_transaction_id": "pending-old-1",
        }
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(
                ingestor,
                "_request_sync_page",
                return_value=_sync_page(added=[added], removed=[{"transaction_id": "explicitly-removed-1"}]),
            ),
        ):
            result = ingestor.sync_transactions({})

        self.assertEqual(set(result.removed_ids), {"pending-old-1", "explicitly-removed-1"})

    def test_null_pending_transaction_id_not_added_to_removed_ids(self) -> None:
        ingestor = _ingestor()
        added = {
            "transaction_id": "settled-1",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "name": "Merchant",
            "amount": 10.0,
            "pending": False,
            "pending_transaction_id": None,
        }
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_sync_page", return_value=_sync_page(added=[added])),
        ):
            result = ingestor.sync_transactions({})

        self.assertEqual(result.removed_ids, [])


class SyncCursorFingerprintTests(unittest.TestCase):
    def test_cursors_keyed_by_sha256_fingerprint_never_the_raw_token(self) -> None:
        token = "token-123456"
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=[token])
        expected_fingerprint = hashlib.sha256(token.encode()).hexdigest()
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(
                ingestor, "_request_sync_page", return_value=_sync_page(next_cursor="next-cursor-value")
            ),
        ):
            result = ingestor.sync_transactions({})

        self.assertEqual(set(result.cursors.keys()), {expected_fingerprint})
        self.assertEqual(result.cursors[expected_fingerprint], "next-cursor-value")
        for key in result.cursors:
            self.assertNotEqual(key, token)
            self.assertNotIn(token, key)

    def test_stored_cursor_lookup_uses_fingerprint_key(self) -> None:
        # If sync_transactions looked up stored_cursors by raw token instead of fingerprint,
        # a stored cursor keyed by fingerprint would never be found and every run would look
        # like a full refresh forever.
        token = "token-123456"
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=[token])
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_sync_page", return_value=_sync_page()) as mock_page,
        ):
            result = ingestor.sync_transactions({fingerprint: "stored-cursor-abc"})

        self.assertFalse(result.full_refresh)
        mock_page.assert_called_once_with(token, "stored-cursor-abc")


class SyncErrorRetryTests(unittest.TestCase):
    def test_mutation_during_pagination_retries_then_succeeds(self) -> None:
        ingestor = _ingestor()
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(
                ingestor,
                "_request_sync_page",
                side_effect=[
                    _http_error("TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"),
                    _sync_page(next_cursor="cursor-final"),
                ],
            ) as mock_page,
        ):
            result = ingestor.sync_transactions({})

        self.assertEqual(mock_page.call_count, 2)
        self.assertEqual(list(result.cursors.values()), ["cursor-final"])

    def test_pagination_invalid_cursor_resets_to_full_refresh_then_succeeds(self) -> None:
        ingestor = _ingestor()
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(
                ingestor,
                "_request_sync_page",
                side_effect=[
                    _http_error("PAGINATION_INVALID_CURSOR"),
                    _sync_page(next_cursor="cursor-after-reset"),
                ],
            ) as mock_page,
        ):
            result = ingestor.sync_transactions({"some-fingerprint": "now-invalid-cursor"})

        self.assertEqual(mock_page.call_count, 2)
        self.assertEqual(list(result.cursors.values()), ["cursor-after-reset"])
        # The retried call must restart from a null cursor, not the invalid stored one.
        self.assertIsNone(mock_page.call_args_list[1][0][1])

    def test_exceeding_retry_cap_raises_rather_than_looping_forever(self) -> None:
        from ingestion.plaid_ingestor import _MAX_SYNC_ERROR_RETRIES

        ingestor = _ingestor()
        fingerprint = hashlib.sha256(b"token-123456").hexdigest()
        error = _http_error("PAGINATION_INVALID_CURSOR")
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_sync_page", side_effect=error) as mock_page,
        ):
            result = ingestor.sync_transactions({})

        # The error is caught by per-token isolation after exceeding retry cap
        self.assertEqual(mock_page.call_count, _MAX_SYNC_ERROR_RETRIES + 1)
        self.assertIn(fingerprint, result.failed_tokens)
        self.assertEqual(result.failed_tokens[fingerprint], "PAGINATION_INVALID_CURSOR")

    def test_unrelated_http_error_is_not_retried(self) -> None:
        ingestor = _ingestor()
        fingerprint = hashlib.sha256(b"token-123456").hexdigest()
        error = _http_error("INVALID_ACCESS_TOKEN")
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(ingestor, "_request_sync_page", side_effect=error) as mock_page,
        ):
            result = ingestor.sync_transactions({})

        # Unrelated errors are not retried; they're caught by per-token isolation on first failure
        mock_page.assert_called_once()
        self.assertIn(fingerprint, result.failed_tokens)
        self.assertEqual(result.failed_tokens[fingerprint], "INVALID_ACCESS_TOKEN")


class SyncClaimAccountsTests(unittest.TestCase):
    def test_co_owned_account_is_skipped_for_the_later_token(self) -> None:
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
            patch.object(ingestor, "_request_sync_page", return_value=_sync_page()),
        ):
            result = ingestor.sync_transactions({})

        self.assertEqual(result.duplicate_accounts_skipped, 1)

    def test_transactions_on_the_skipped_account_are_dropped(self) -> None:
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

        txn_on_skipped_account = {
            "transaction_id": "txn-1",
            "account_id": "acc-b",
            "date": "2026-08-01",
            "name": "Duplicate view of a joint account transaction",
            "amount": 42.0,
        }

        with (
            patch.object(ingestor, "_fetch_accounts_raw", side_effect=[[account_a], [account_b]]),
            patch.object(
                ingestor,
                "_request_sync_page",
                side_effect=[_sync_page(), _sync_page(added=[txn_on_skipped_account])],
            ),
        ):
            result = ingestor.sync_transactions({})

        self.assertTrue(result.added.empty)


class SyncPerTokenIsolationTests(unittest.TestCase):
    def test_sync_transactions_isolates_non_recoverable_error_to_failed_tokens(self) -> None:
        """When one of three tokens fails with a non-recoverable error (not a retry-able code),
        that token should be skipped and recorded in failed_tokens, while other tokens' data
        is included in the result."""
        token_1 = "token-111111"
        token_2 = "token-222222"
        token_3 = "token-333333"
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=[token_1, token_2, token_3])

        fp_1 = hashlib.sha256(token_1.encode()).hexdigest()
        fp_2 = hashlib.sha256(token_2.encode()).hexdigest()
        fp_3 = hashlib.sha256(token_3.encode()).hexdigest()

        txn_1 = {
            "transaction_id": "txn-from-token-1",
            "account_id": "acc-1",
            "date": "2026-08-01",
            "name": "Merchant A",
            "amount": 10.0,
        }
        txn_3 = {
            "transaction_id": "txn-from-token-3",
            "account_id": "acc-3",
            "date": "2026-08-02",
            "name": "Merchant C",
            "amount": 30.0,
        }

        # Mock _fetch_accounts_raw to return empty lists (no account filtering needed for this test)
        with (
            patch.object(ingestor, "_fetch_accounts_raw", return_value=[]),
            patch.object(
                ingestor,
                "_request_sync_page",
                side_effect=[
                    _sync_page(added=[txn_1], next_cursor="cursor-1"),  # token 1 succeeds
                    _http_error("ITEM_LOGIN_REQUIRED"),  # token 2 fails with non-recoverable error
                    _sync_page(added=[txn_3], next_cursor="cursor-3"),  # token 3 succeeds
                ],
            ),
        ):
            result = ingestor.sync_transactions({})

        # Assert: added data contains rows from token 1 and 3, but not token 2
        self.assertEqual(len(result.added), 2)
        fingerprints_in_result = set(result.added["_token_fingerprint"].unique())
        self.assertEqual(fingerprints_in_result, {fp_1, fp_3})
        self.assertNotIn(fp_2, fingerprints_in_result)

        # Assert: failed_tokens contains only token 2's fingerprint
        self.assertEqual(len(result.failed_tokens), 1)
        self.assertIn(fp_2, result.failed_tokens)
        self.assertEqual(result.failed_tokens[fp_2], "ITEM_LOGIN_REQUIRED")

        # Assert: cursors contains entries for token 1 and 3, but not token 2
        self.assertEqual(set(result.cursors.keys()), {fp_1, fp_3})
        self.assertEqual(result.cursors[fp_1], "cursor-1")
        self.assertEqual(result.cursors[fp_3], "cursor-3")


class FetchAccountsPerTokenIsolationTests(unittest.TestCase):
    def test_fetch_accounts_isolates_token_failure_to_failed_tokens(self) -> None:
        """When one of two tokens fails, that token should be skipped and recorded in
        failed_tokens, while the other token's accounts are included in the result."""
        token_1 = "token-111111"
        token_2 = "token-222222"
        ingestor = PlaidIngestor(client_id="cid", secret="secret", access_tokens=[token_1, token_2])

        fp_1 = hashlib.sha256(token_1.encode()).hexdigest()
        fp_2 = hashlib.sha256(token_2.encode()).hexdigest()

        account_2 = {
            "account_key": "plaid:acc-2",
            "account_name": "Checking (••••5678)",
            "official_name": "Chequing Account",
            "account_type": "depository",
            "account_subtype": "checking",
            "persistent_account_id": "persist-2",
            "mask": "5678",
            "balance_available": 1000.0,
            "balance_current": 1000.0,
            "balance_limit": None,
            "iso_currency_code": "USD",
            "source": "plaid",
            "_account_id": "acc-2",
        }

        def side_effect_fetch_raw(token: str, owner_name: str) -> list[dict]:
            if token == token_1:
                raise requests.RequestException("Connection failed")
            return [account_2]

        with patch.object(ingestor, "_fetch_accounts_raw", side_effect=side_effect_fetch_raw):
            accounts, failed_tokens = ingestor.fetch_accounts({})

        # Assert: returned accounts list contains only token 2's accounts
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["_account_id"], "acc-2")
        self.assertEqual(accounts[0]["_token_fingerprint"], fp_2)

        # Assert: failed_tokens contains only token 1's fingerprint
        self.assertEqual(len(failed_tokens), 1)
        self.assertIn(fp_1, failed_tokens)
        self.assertEqual(failed_tokens[fp_1], "RequestException")

        # Assert: token 2's account has the correct fingerprint
        self.assertEqual(accounts[0]["_token_fingerprint"], fp_2)


if __name__ == "__main__":
    unittest.main()
