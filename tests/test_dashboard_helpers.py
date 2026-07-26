from __future__ import annotations

import unittest

import pandas as pd

from app.dashboard import _classify_tx_type, _label_subtype


def _frame(account_type, amount: float, description: str = "Some Merchant") -> pd.DataFrame:
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


class ClassifyTxTypeMatrixTests(unittest.TestCase):
    def test_depository_negative_is_income(self) -> None:
        df = _frame("depository", -100.0)
        self.assertEqual(_classify_tx_type(df).iloc[0], "income")

    def test_depository_positive_payment_is_transfer(self) -> None:
        df = _frame("depository", 100.0, "Credit Card Payment")
        self.assertEqual(_classify_tx_type(df).iloc[0], "transfer")

    def test_depository_positive_no_keyword_is_expense(self) -> None:
        df = _frame("depository", 100.0, "Groceries")
        self.assertEqual(_classify_tx_type(df).iloc[0], "expense")

    def test_credit_positive_is_expense(self) -> None:
        df = _frame("credit", 50.0)
        self.assertEqual(_classify_tx_type(df).iloc[0], "expense")

    def test_credit_negative_refund_is_income(self) -> None:
        df = _frame("credit", -25.0, "Cashback reward")
        self.assertEqual(_classify_tx_type(df).iloc[0], "expense")

    def test_credit_negative_no_refund_is_transfer(self) -> None:
        df = _frame("credit", -350.0, "Payment - Thank You")
        self.assertEqual(_classify_tx_type(df).iloc[0], "transfer")

    def test_unknown_account_type_negative_is_income(self) -> None:
        df = _frame(None, -500.0)
        self.assertEqual(_classify_tx_type(df).iloc[0], "income")

    def test_unknown_account_type_positive_is_expense(self) -> None:
        df = _frame(None, 30.0)
        self.assertEqual(_classify_tx_type(df).iloc[0], "expense")

    def test_investment_negative_is_income(self) -> None:
        df = _frame("investment", -200.0)
        self.assertEqual(_classify_tx_type(df).iloc[0], "income")


class LabelSubtypeTests(unittest.TestCase):
    def test_known_subtype_en(self) -> None:
        self.assertEqual(_label_subtype("tfsa", "en"), "TFSA")

    def test_known_subtype_fr(self) -> None:
        self.assertEqual(_label_subtype("checking", "fr"), "Compte-chèques")

    def test_unknown_subtype_titlecased(self) -> None:
        self.assertEqual(_label_subtype("brokerage", "en"), "Brokerage")

    def test_none_subtype(self) -> None:
        self.assertEqual(_label_subtype(None, "en"), "Other")


if __name__ == "__main__":
    unittest.main()
