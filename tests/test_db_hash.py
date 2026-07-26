from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal

import pandas as pd

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

        self.assertEqual(build_transaction_hash(same_account), build_transaction_hash(renamed_account))
        self.assertNotEqual(build_transaction_hash(same_account), build_transaction_hash(different_account))

    def test_hash_is_type_independent(self) -> None:
        """Regression test: the same transaction must hash identically whether amount
        arrives as a pipeline float, a Postgres Decimal, an int, or a plain string.
        This is the bug that caused post-rehash pipeline runs to duplicate every
        transaction whose amount rendered differently under float vs Decimal str()."""
        for amount_value in (100, -2800, 12.5, 17.99):
            base = {
                "account_key": "plaid:abc123",
                "date": "2026-07-01",
                "description": "Payroll - Direct Deposit",
            }
            float_form = build_transaction_hash({**base, "amount": float(amount_value)})
            decimal_form = build_transaction_hash(
                {**base, "amount": Decimal(str(amount_value)).quantize(Decimal("0.01"))}
            )
            int_form = build_transaction_hash({**base, "amount": amount_value})
            str_form = build_transaction_hash({**base, "amount": f"{amount_value:.2f}"})
            self.assertEqual(float_form, decimal_form, msg=f"amount={amount_value}")
            self.assertEqual(float_form, int_form, msg=f"amount={amount_value}")
            self.assertEqual(float_form, str_form, msg=f"amount={amount_value}")

    def test_hash_is_date_type_independent(self) -> None:
        base = {
            "account_key": "plaid:abc123",
            "description": "Coffee Shop",
            "amount": 5.25,
        }
        date_form = build_transaction_hash({**base, "date": dt.date(2026, 7, 1)})
        datetime_form = build_transaction_hash({**base, "date": dt.datetime(2026, 7, 1)})
        timestamp_form = build_transaction_hash({**base, "date": pd.Timestamp("2026-07-01")})
        str_form = build_transaction_hash({**base, "date": "2026-07-01"})

        self.assertEqual(date_form, datetime_form)
        self.assertEqual(date_form, timestamp_form)
        self.assertEqual(date_form, str_form)

    def test_hash_still_differs_on_real_differences(self) -> None:
        """Canonicalization must not collapse genuinely different transactions."""
        base = {
            "account_key": "plaid:abc123",
            "date": "2026-07-01",
            "description": "Coffee Shop",
            "amount": 5.25,
        }
        different_amount = {**base, "amount": 5.26}
        different_date = {**base, "date": "2026-07-02"}
        different_description = {**base, "description": "Tea Shop"}
        different_account = {**base, "account_key": "plaid:xyz789"}

        base_hash = build_transaction_hash(base)
        self.assertNotEqual(base_hash, build_transaction_hash(different_amount))
        self.assertNotEqual(base_hash, build_transaction_hash(different_date))
        self.assertNotEqual(base_hash, build_transaction_hash(different_description))
        self.assertNotEqual(base_hash, build_transaction_hash(different_account))


if __name__ == "__main__":
    unittest.main()
