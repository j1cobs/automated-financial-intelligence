from __future__ import annotations

import unittest

import pandas as pd
import plotly.graph_objects as go

from app.dashboard import (
    _classify_tx_type,
    _effective_credit_limit,
    _label_subtype,
    _style_chart,
)
from app.streamlit_app import _CSS_PATH


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


class EffectiveCreditLimitTests(unittest.TestCase):
    def test_plaid_limit_present_wins(self) -> None:
        limit, is_manual = _effective_credit_limit(2000.0, 5000.0)
        self.assertEqual(limit, 2000.0)
        self.assertFalse(is_manual)

    def test_plaid_missing_falls_back_to_manual(self) -> None:
        limit, is_manual = _effective_credit_limit(float("nan"), 3000.0)
        self.assertEqual(limit, 3000.0)
        self.assertTrue(is_manual)

    def test_neither_present_is_unknown(self) -> None:
        limit, is_manual = _effective_credit_limit(float("nan"), float("nan"))
        self.assertIsNone(limit)
        self.assertFalse(is_manual)

    def test_zero_plaid_limit_treated_as_missing(self) -> None:
        limit, is_manual = _effective_credit_limit(0.0, 1000.0)
        self.assertEqual(limit, 1000.0)
        self.assertTrue(is_manual)


class MobileStylesheetTests(unittest.TestCase):
    """Guard the responsive stylesheet.

    A rename, a bad path, or a lost file produces no exception and no warning -- the app
    just silently renders unstyled. That is the same silent-failure class documented in
    PLAN.md's "module-level st.* calls" gotcha, so it gets a test rather than trust.
    """

    def test_stylesheet_exists_and_is_populated(self) -> None:
        self.assertTrue(_CSS_PATH.is_file(), f"missing stylesheet: {_CSS_PATH}")
        self.assertTrue(_CSS_PATH.read_text(encoding="utf-8").strip())

    def test_stylesheet_contains_no_literal_style_tag(self) -> None:
        """A literal style tag anywhere in the file silently voids the whole stylesheet.

        st.html() wraps this file in one style tag; a stray inner one corrupts the block
        during sanitisation and every rule is dropped -- no browser console error, no
        server-log warning. Verified empirically 2026-07-27: a file whose only sin was
        the text "<style>" inside a CSS comment registered zero rules, while the same
        file without it registered all of them.
        """
        css = _CSS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("<style", css.lower())
        self.assertNotIn("</style", css.lower())

    def test_stylesheet_defines_the_mobile_breakpoint(self) -> None:
        css = _CSS_PATH.read_text(encoding="utf-8")
        self.assertIn("max-width: 640px", css)
        # The 2-up metric rule is the highest-leverage change in the phase; if the
        # :has() selector is ever dropped, this fails loudly instead of quietly
        # reverting the Overview tab to a six-card scroll.
        self.assertIn('[data-testid="stMetric"]', css)


class StyleChartTests(unittest.TestCase):
    def test_applies_mobile_layout(self) -> None:
        fig = _style_chart(go.Figure())
        self.assertEqual(fig.layout.height, 320)
        self.assertEqual(fig.layout.legend.orientation, "h")
        self.assertEqual(fig.layout.margin.l, 8)
        self.assertEqual(fig.layout.hovermode, "x unified")

    def test_height_is_overridable(self) -> None:
        self.assertEqual(_style_chart(go.Figure(), height=380).layout.height, 380)

    def test_hovermode_none_leaves_plotly_default(self) -> None:
        """Pie charts have no x-axis for 'x unified' to unify along."""
        fig = _style_chart(go.Figure(), hovermode=None)
        self.assertNotEqual(fig.layout.hovermode, "x unified")
        self.assertEqual(fig.layout.height, 320)

    def test_hovermode_is_overridable(self) -> None:
        fig = _style_chart(go.Figure(), hovermode="y unified")
        self.assertEqual(fig.layout.hovermode, "y unified")


if __name__ == "__main__":
    unittest.main()
