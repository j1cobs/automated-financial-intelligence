from __future__ import annotations

import logging

import streamlit as st

from app.auth import render_sidebar, render_sign_in
from app.dashboard import load_financial_data, render_dashboard
from core.config import load_settings

LOGGER = logging.getLogger(__name__)


def main() -> None:
    st.set_page_config(page_title="Automated Financial Intelligence", layout="wide")
    st.html(
        '<style>[data-testid="stMainBlockContainer"] '
        "{max-width: 100%; padding-left: 2rem; padding-right: 2rem;}</style>"
    )

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
