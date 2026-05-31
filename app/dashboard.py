from __future__ import annotations

import altair as alt
import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st


def load_transactions(database_url: str) -> pd.DataFrame:
    query = """
    SELECT
        transaction_date AS date,
        account_key,
        description,
        amount::double precision AS amount,
        category,
        outlier_score,
        is_outlier
    FROM transactions
    ORDER BY transaction_date DESC
    """
    with psycopg.connect(database_url) as connection:
        return pd.read_sql(query, connection)


def render_dashboard(frame: pd.DataFrame) -> None:
    st.title("Automated Financial Intelligence")
    if frame.empty:
        st.info("No transactions available.")
        return

    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame["month"] = frame["date"].dt.to_period("M").astype(str)

    col1, col2 = st.columns(2)
    with col1:
        burn = frame.groupby("date", as_index=False)["amount"].sum().sort_values("date")
        burn["rolling_30d"] = burn["amount"].rolling(30, min_periods=1).sum()
        st.plotly_chart(
            px.line(burn, x="date", y="rolling_30d", title="Rolling 30-day Burn Rate"),
            use_container_width=True,
        )

    with col2:
        split = frame.groupby(["month", "account_key"], as_index=False)["amount"].sum()
        st.altair_chart(
            alt.Chart(split)
            .mark_bar()
            .encode(x="month:N", y="amount:Q", color="account_key:N")
            .properties(title="Combined vs Individual Budget Breakdown"),
            use_container_width=True,
        )

    dist = frame.groupby(["month", "category"], as_index=False)["amount"].sum()
    st.plotly_chart(
        px.bar(
            dist,
            x="month",
            y="amount",
            color="category",
            title="Monthly Category Distribution",
        ),
        use_container_width=True,
    )

    st.subheader("Flagged Outliers")
    st.dataframe(
        frame[frame["is_outlier"]][
            [
                "date",
                "account_key",
                "description",
                "amount",
                "category",
                "outlier_score",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )
