from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from analytics.enrichment import classify_tx_type, detect_internal_transfers, effective_credit_limit


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _row_frame(account_type, amount: float, description: str = "Some Merchant") -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "account_type": account_type,
                "account_name": "Test Account",
                "amount": amount,
                "description": description,
                "date": pd.Timestamp("2026-01-01"),
            }
        ]
    )
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        types = classify_tx_type(df)
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
        paired = detect_internal_transfers(df)
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
        paired = detect_internal_transfers(df)
        self.assertFalse(paired.any())
        types = classify_tx_type(df)
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
        paired = detect_internal_transfers(df)
        self.assertEqual(int(paired.sum()), 2)


if __name__ == "__main__":
    unittest.main()


class ClassifyTxTypeMatrixTests(unittest.TestCase):
    def test_depository_negative_is_income(self) -> None:
        df = _row_frame("depository", -100.0)
        self.assertEqual(classify_tx_type(df).iloc[0], "income")

    def test_depository_positive_payment_is_transfer(self) -> None:
        df = _row_frame("depository", 100.0, "Credit Card Payment")
        self.assertEqual(classify_tx_type(df).iloc[0], "transfer")

    def test_depository_positive_no_keyword_is_expense(self) -> None:
        df = _row_frame("depository", 100.0, "Groceries")
        self.assertEqual(classify_tx_type(df).iloc[0], "expense")

    def test_credit_positive_is_expense(self) -> None:
        df = _row_frame("credit", 50.0)
        self.assertEqual(classify_tx_type(df).iloc[0], "expense")

    def test_credit_negative_refund_is_income(self) -> None:
        df = _row_frame("credit", -25.0, "Cashback reward")
        self.assertEqual(classify_tx_type(df).iloc[0], "expense")

    def test_credit_negative_no_refund_is_transfer(self) -> None:
        df = _row_frame("credit", -350.0, "Payment - Thank You")
        self.assertEqual(classify_tx_type(df).iloc[0], "transfer")

    def test_unknown_account_type_negative_is_income(self) -> None:
        df = _row_frame(None, -500.0)
        self.assertEqual(classify_tx_type(df).iloc[0], "income")

    def test_unknown_account_type_positive_is_expense(self) -> None:
        df = _row_frame(None, 30.0)
        self.assertEqual(classify_tx_type(df).iloc[0], "expense")

    def test_investment_negative_is_income(self) -> None:
        df = _row_frame("investment", -200.0)
        self.assertEqual(classify_tx_type(df).iloc[0], "income")


class EffectiveCreditLimitTests(unittest.TestCase):
    def test_plaid_limit_present_wins(self) -> None:
        limit, is_manual = effective_credit_limit(2000.0, 5000.0)
        self.assertEqual(limit, 2000.0)
        self.assertFalse(is_manual)

    def test_plaid_missing_falls_back_to_manual(self) -> None:
        limit, is_manual = effective_credit_limit(float("nan"), 3000.0)
        self.assertEqual(limit, 3000.0)
        self.assertTrue(is_manual)

    def test_neither_present_is_unknown(self) -> None:
        limit, is_manual = effective_credit_limit(float("nan"), float("nan"))
        self.assertIsNone(limit)
        self.assertFalse(is_manual)

    def test_zero_plaid_limit_treated_as_missing(self) -> None:
        limit, is_manual = effective_credit_limit(0.0, 1000.0)
        self.assertEqual(limit, 1000.0)
        self.assertTrue(is_manual)
