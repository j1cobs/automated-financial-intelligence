from __future__ import annotations

import logging

# import sys
# from pathlib import Path

# # Adds the root directory (one level up from 'app') to the Python path
# root_path = Path(__file__).resolve().parent.parent
# if str(root_path) not in sys.path:
#     sys.path.append(str(root_path))

import streamlit as st

from core.config import load_settings
from app.auth import render_sidebar, render_sign_in
from app.dashboard import load_financial_data, render_dashboard

LOGGER = logging.getLogger(__name__)

st.set_page_config(page_title="Automated Financial Intelligence", layout="wide")


def main() -> None:
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
