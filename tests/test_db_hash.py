from __future__ import annotations

import unittest

from database.db import build_transaction_hash


class TransactionHashTests(unittest.TestCase):
    def test_hash_is_stable_for_same_transaction(self) -> None:
        payload = {
            "account_key": "plaid:abc123",
            "date": "2026-01-02",
            "description": "Coffee Shop",
            "amount": 5.25,
        }
        self.assertEqual(build_transaction_hash(payload), build_transaction_hash(payload))

    def test_hash_differs_by_account_key_not_account_name(self) -> None:
        base = {"date": "2026-01-02", "description": "Coffee Shop", "amount": 5.25}
        same_account = {**base, "account_key": "plaid:abc123", "account_name": "Checking"}
        renamed_account = {**base, "account_key": "plaid:abc123", "account_name": "Checking ••••9999"}
        different_account = {**base, "account_key": "plaid:xyz789"}

        self.assertEqual(
            build_transaction_hash(same_account), build_transaction_hash(renamed_account)
        )
        self.assertNotEqual(
            build_transaction_hash(same_account), build_transaction_hash(different_account)
        )


if __name__ == "__main__":
    unittest.main()
