from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from app.dashboard import _classify_tx_type, _detect_internal_transfers


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


class ClassifyTxTypeTests(unittest.TestCase):
    def test_credit_refund_nets_to_expense_not_income(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": -50.0,
                    "description": "Refund - Store Return",
                    "date": date(2026, 1, 5),
                }
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "expense")

    def test_credit_payment_with_keyword_is_transfer(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": -350.0,
                    "description": "Payment - Thank You",
                    "date": date(2026, 1, 20),
                }
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "transfer")

    def test_credit_negative_no_keyword_is_transfer(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": -200.0,
                    "description": "Some Card Credit",
                    "date": date(2026, 1, 10),
                }
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "transfer")

    def test_credit_purchase_is_expense(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": 80.0,
                    "description": "Electronics Store",
                    "date": date(2026, 1, 3),
                }
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "expense")

    def test_no_credit_row_is_ever_income(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": 80.0,
                    "description": "Electronics Store",
                    "date": date(2026, 1, 3),
                },
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": -50.0,
                    "description": "Refund - Store Return",
                    "date": date(2026, 1, 5),
                },
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": -350.0,
                    "description": "Payment - Thank You",
                    "date": date(2026, 1, 20),
                },
                {
                    "account_type": "credit",
                    "account_name": "Visa",
                    "amount": -200.0,
                    "description": "Some Card Credit",
                    "date": date(2026, 1, 10),
                },
            ]
        )
        types = _classify_tx_type(df)
        is_credit = df["account_type"] == "credit"
        self.assertFalse((types[is_credit] == "income").any())

    def test_unpaired_payroll_is_income(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": -2800.0,
                    "description": "Payroll - Direct Deposit",
                    "date": date(2026, 1, 1),
                }
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "income")

    def test_unpaired_incoming_etransfer_is_income(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": -500.0,
                    "description": "Interac e-Transfer received",
                    "date": date(2026, 1, 8),
                }
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "income")

    def test_paired_cross_account_legs_are_both_transfer(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": 500.0,
                    "description": "Transfer to Savings",
                    "date": date(2026, 1, 10),
                },
                {
                    "account_type": "depository",
                    "account_name": "Sam Chequing",
                    "amount": -500.0,
                    "description": "Transfer received",
                    "date": date(2026, 1, 12),
                },
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "transfer")
        self.assertEqual(types.iloc[1], "transfer")

    def test_seed_script_credit_card_payment_pair_both_transfer(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "credit",
                    "account_name": "Alex Rewards Visa",
                    "amount": -350.0,
                    "description": "Payment - Thank You",
                    "date": date(2026, 1, 20),
                },
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": 350.0,
                    "description": "Credit Card Payment",
                    "date": date(2026, 1, 20),
                },
            ]
        )
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[0], "transfer")
        self.assertEqual(types.iloc[1], "transfer")


class DetectInternalTransfersTests(unittest.TestCase):
    def test_same_account_legs_are_not_paired(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": 500.0,
                    "description": "Withdrawal",
                    "date": date(2026, 1, 10),
                },
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": -500.0,
                    "description": "Deposit",
                    "date": date(2026, 1, 11),
                },
            ]
        )
        paired = _detect_internal_transfers(df)
        self.assertFalse(paired.any())

    def test_out_of_window_legs_are_not_paired(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": 500.0,
                    "description": "Transfer out",
                    "date": date(2026, 1, 1),
                },
                {
                    "account_type": "depository",
                    "account_name": "Sam Chequing",
                    "amount": -500.0,
                    "description": "Transfer in",
                    "date": date(2026, 1, 9),
                },
            ]
        )
        paired = _detect_internal_transfers(df)
        self.assertFalse(paired.any())
        types = _classify_tx_type(df)
        self.assertEqual(types.iloc[1], "income")

    def test_greedy_one_to_one_matching(self) -> None:
        df = _frame(
            [
                {
                    "account_type": "depository",
                    "account_name": "Alex Chequing",
                    "amount": 500.0,
                    "description": "Transfer out 1",
                    "date": date(2026, 1, 1),
                },
                {
                    "account_type": "depository",
                    "account_name": "Sam Chequing",
                    "amount": 500.0,
                    "description": "Transfer out 2",
                    "date": date(2026, 1, 2),
                },
                {
                    "account_type": "depository",
                    "account_name": "Alex TFSA",
                    "amount": -500.0,
                    "description": "Transfer in",
                    "date": date(2026, 1, 3),
                },
            ]
        )
        paired = _detect_internal_transfers(df)
        self.assertEqual(int(paired.sum()), 2)


if __name__ == "__main__":
    unittest.main()
