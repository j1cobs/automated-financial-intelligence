from __future__ import annotations

import unittest

import plotly.graph_objects as go

from app.dashboard import _style_chart
from app.streamlit_app import _CSS_PATH


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
