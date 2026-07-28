from __future__ import annotations

import logging
import pathlib

import streamlit as st

from app.auth import render_sidebar, render_sign_in
from app.dashboard import load_financial_data, render_dashboard
from core.config import load_settings

LOGGER = logging.getLogger(__name__)

_CSS_PATH = pathlib.Path(__file__).parent / "static" / "mobile.css"


def _inject_css() -> None:
    """Load the app stylesheet once per render.

    st.html() wraps a .css file in <style> tags and routes style-only content to the
    event container, so this costs zero layout space. DOMPurify keeps <style> and does
    not touch rule contents, so @media queries survive -- no unsafe_allow_html needed.

    Called from main() rather than render_dashboard() on purpose: main() returns early
    when the user is not signed in, so injecting downstream would leave the sign-in
    page -- the first screen every mobile user sees -- completely unstyled.

    The path resolves from __file__, not the CWD: every other path in this repo is
    CWD-relative, but a stylesheet must not silently vanish when the app is launched
    from another directory.
    """
    st.html(_CSS_PATH)


def main() -> None:
    st.set_page_config(
        page_title="Automated Financial Intelligence",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_css()

    settings = load_settings()

    render_sidebar(settings)

    if not render_sign_in(settings):
        return

    try:
        tx_data, acct_data = load_financial_data(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to load dashboard data")
        st.error("Failed to load dashboard data — check the server logs.")
        return

    render_dashboard(tx_data, acct_data, settings.database_url)


if __name__ == "__main__":
    main()
