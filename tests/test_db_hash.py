from __future__ import annotations

import unittest

from database.db import build_transaction_hash


class TransactionHashTests(unittest.TestCase):
    def test_hash_is_stable_for_same_transaction(self) -> None:
        payload = {
            "account_name": "Checking",
            "date": "2026-01-02",
            "description": "Coffee Shop",
            "amount": 5.25,
        }
        self.assertEqual(build_transaction_hash(payload), build_transaction_hash(payload))


if __name__ == "__main__":
    unittest.main()
