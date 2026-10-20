"""Phase 35: on-demand balance refresh.

Balances are otherwise only as fresh as the last pipeline run -- up to 24 hours
stale -- which makes goal progress and net worth read as wrong right after money
moves. `/accounts/balance/get` needs no re-link and works with existing tokens.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from ingestion.plaid_ingestor import PlaidIngestor


def _ingestor(tokens=("token-a",)) -> PlaidIngestor:
    return PlaidIngestor(
        client_id="cid",
        secret="secret",
        access_tokens=list(tokens),
        base_url="https://sandbox.plaid.com",
    )


def _account(account_id="acc1", current=1234.56):
    return {
        "account_id": account_id,
        "name": "Chequing",
        "official_name": "Alex Chequing",
        "type": "depository",
        "subtype": "checking",
        "mask": "1234",
        "persistent_account_id": "p1",
        "balances": {"current": current, "available": current, "limit": None, "iso_currency_code": "CAD"},
    }


class RefreshBalancesTests(unittest.TestCase):
    def test_calls_the_balance_endpoint_not_accounts_get(self):
        """`/accounts/get` may serve Plaid's cached balance; the whole point of
        this call is to force a fetch from the institution."""
        ingestor = _ingestor()
        with patch.object(ingestor, "_post", return_value={"accounts": [_account()]}) as post:
            ingestor.refresh_balances()

        endpoint = post.call_args[0][0]
        self.assertEqual(endpoint, "accounts/balance/get")

    def test_returns_accounts_in_the_same_shape_as_fetch_accounts(self):
        ingestor = _ingestor()
        with patch.object(ingestor, "_post", return_value={"accounts": [_account()]}):
            accounts, failed = ingestor.refresh_balances({"token-a": "Alex"})

        self.assertEqual(failed, {})
        self.assertEqual(len(accounts), 1)
        account = accounts[0]
        self.assertEqual(account["account_key"], "plaid:acc1")
        self.assertEqual(account["owner_name"], "Alex")
        self.assertEqual(account["balance_current"], 1234.56)
        self.assertIn("_token_fingerprint", account)

    def test_bypasses_the_cached_raw_accounts(self):
        """Reusing the per-instance cache would defeat the purpose."""
        ingestor = _ingestor()
        ingestor._raw_accounts_cache["token-a"] = [_account(current=1.0)]

        with patch.object(ingestor, "_post", return_value={"accounts": [_account(current=999.0)]}):
            accounts, _ = ingestor.refresh_balances()

        self.assertEqual(accounts[0]["balance_current"], 999.0)

    def test_one_broken_item_does_not_stop_the_others(self):
        ingestor = _ingestor(tokens=("token-a", "token-b"))

        def side_effect(endpoint, payload):
            if payload["access_token"] == "token-a":
                raise RuntimeError("ITEM_LOGIN_REQUIRED")
            return {"accounts": [_account(account_id="acc2")]}

        with patch.object(ingestor, "_post", side_effect=side_effect):
            accounts, failed = ingestor.refresh_balances()

        self.assertEqual(len(accounts), 1)
        self.assertEqual(len(failed), 1)

    def test_failure_logging_never_includes_the_response_body(self):
        """Pipeline/API stdout can reach the GitHub Actions log."""
        ingestor = _ingestor()
        with patch.object(ingestor, "_post", side_effect=RuntimeError("secret-account-detail")):
            with self.assertLogs("ingestion.plaid_ingestor", level="WARNING") as captured:
                _accounts, failed = ingestor.refresh_balances()

        self.assertEqual(len(failed), 1)
        joined = "\n".join(captured.output)
        self.assertNotIn("1234", joined)  # no account mask


class SnapshotUpsertTests(unittest.TestCase):
    def test_same_day_refresh_updates_in_place(self):
        """account_balance_snapshots is UNIQUE (account_key, snapshot_date), so
        refreshing twice in a day must not create a second row for that day."""
        from database.db import DatabaseClient

        client = DatabaseClient("postgresql://x/y")
        with patch.object(client, "_execute_many") as execute_many:
            client.record_balance_snapshots(
                [{"account_key": "plaid:acc1", "balance_current": 10.0, "balance_available": 10.0}]
            )

        sql = execute_many.call_args[0][0]
        self.assertIn("ON CONFLICT (account_key, snapshot_date) DO UPDATE", sql)


if __name__ == "__main__":
    unittest.main()
