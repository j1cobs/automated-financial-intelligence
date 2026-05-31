from __future__ import annotations

import streamlit as st

from core.config import load_settings
from app.auth import render_sidebar, render_sign_in
from app.dashboard import load_transactions, render_dashboard

st.set_page_config(page_title="Automated Financial Intelligence", layout="wide")


def main() -> None:
    settings = load_settings()

    render_sidebar(settings)

    if not render_sign_in(settings):
        return

    try:
        data = load_transactions(settings.database_url)
    except Exception as error:
        st.error(f"Failed to load dashboard data: {error}")
        return

    render_dashboard(data)


if __name__ == "__main__":
    main()
