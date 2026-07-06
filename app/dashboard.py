from __future__ import annotations

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st

_SUBTYPE_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "rrsp": "RRSP",
        "tfsa": "TFSA",
        "fhsa": "FHSA",
        "checking": "Chequing",
        "savings": "Savings",
        "credit card": "Credit card",
        "paypal": "PayPal",
    },
    "fr": {
        "rrsp": "REER",
        "tfsa": "CELI",
        "fhsa": "CELIAPP",
        "checking": "Compte-chèques",
        "savings": "Épargne",
        "credit card": "Carte de crédit",
        "paypal": "PayPal",
    },
}

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Automated financial intelligence",
        "toggle_lang": "Français",
        # Sidebar
        "filters": "Filters",
        "period": "Month",
        "owners": "Account holders",
        "categories": "Categories",
        "accounts": "Accounts",
        "amount_range": "Amount range ($)",
        "search": "Search description",
        "outliers_only": "Flagged transactions only",
        # Section 1
        "s1_heading": "Net worth overview",
        "s1_caption": "Total assets minus total liabilities.",
        "metric_net_worth": "Net worth",
        "metric_assets": "Total assets",
        "metric_liabilities": "Total liabilities",
        "chart_asset_mix": "Asset breakdown by account type",
        "chart_owner_balance": "Assets vs. liabilities by holder",
        "credit_util_heading": "Credit card utilisation",
        "credit_util_caption": "Credit limit used per card.",
        "credit_util_label": "{card} — {owner} — {pct:.0f}% used",
        "no_credit": "No credit accounts found.",
        # Section 3
        "s3_heading": "Cash flow analysis",
        "s3_caption": "Inflows are positive, outflows are negative.",
        "metric_income": "Real income",
        "metric_expenses": "Real expenses",
        "metric_net_flow": "Net cash flow",
        "metric_transfers": "Excluded transfers",
        "metric_flags": "Flagged transactions",
        "transfers_note": "Inter-account transfers are excluded from income and expense totals.",
        "burn_caption": "Spend over a rolling 30-day window.",
        "chart_burn": "30-day rolling spend",
        "chart_monthly_net": "Monthly net cash flow by holder",
        "chart_cat_dist": "Monthly expense breakdown by category",
        "axis_amount": "Amount ($)",
        "axis_month": "Month",
        "axis_date": "Date",
        "axis_holder": "Holder",
        # Section 4
        "s4_heading": "Anomaly detection",
        "s4_caption": "Higher score = more unusual transaction.",
        "chart_outlier_scatter": "Unusual transactions — score vs. date",
        "axis_score": "Outlier score",
        "col_date": "Date",
        "col_owner": "Holder",
        "col_account": "Account",
        "col_desc": "Description",
        "col_amount": "Amount ($)",
        "col_cat": "Category",
        "col_score": "Outlier score",
        "no_anomalies": "No anomalies detected in the selected period.",
        # Section 5
        "s5_heading": "Transactions",
        "s5_caption": "Positive amounts are income or credits. Negative amounts are expenses or debits.",
        # Empty states
        "no_accounts": "No account data available.",
        "no_transactions": "No transactions match the selected filters.",
        "no_data": "No data available.",
    },
    "fr": {
        "title": "Intelligence financière automatisée",
        "toggle_lang": "Français",
        "filters": "Filtres",
        "period": "Mois",
        "owners": "Titulaires",
        "categories": "Catégories",
        "accounts": "Comptes",
        "amount_range": "Plage de montants ($)",
        "search": "Rechercher dans la description",
        "outliers_only": "Transactions signalées uniquement",
        "s1_heading": "Aperçu de la valeur nette",
        "s1_caption": "Total des actifs moins le total des dettes.",
        "metric_net_worth": "Valeur nette",
        "metric_assets": "Total des actifs",
        "metric_liabilities": "Total des passifs",
        "chart_asset_mix": "Répartition des actifs par type de compte",
        "chart_owner_balance": "Actifs vs. passifs par titulaire",
        "credit_util_heading": "Utilisation des cartes de crédit",
        "credit_util_caption": "Limite de crédit utilisée par carte.",
        "credit_util_label": "{card} — {owner} — {pct:.0f}% utilisé",
        "no_credit": "Aucun compte de crédit trouvé.",
        "s3_heading": "Analyse des flux monétaires",
        "s3_caption": "Les entrées sont positives, les sorties sont négatives.",
        "metric_income": "Revenus réels",
        "metric_expenses": "Dépenses réelles",
        "metric_net_flow": "Flux net",
        "metric_transfers": "Transferts exclus",
        "metric_flags": "Transactions signalées",
        "transfers_note": "Les transferts entre comptes sont exclus des totaux de revenus et dépenses.",
        "burn_caption": "Dépenses sur une fenêtre de 30 jours glissants.",
        "chart_burn": "Dépenses sur 30 jours glissants",
        "chart_monthly_net": "Flux net mensuel par titulaire",
        "chart_cat_dist": "Répartition mensuelle des dépenses par catégorie",
        "axis_amount": "Montant ($)",
        "axis_month": "Mois",
        "axis_date": "Date",
        "axis_holder": "Titulaire",
        "s4_heading": "Détection des anomalies",
        "s4_caption": "Score plus élevé = transaction plus inhabituelle.",
        "chart_outlier_scatter": "Transactions inhabituelles — score vs. date",
        "axis_score": "Score d'anomalie",
        "col_date": "Date",
        "col_owner": "Titulaire",
        "col_account": "Compte",
        "col_desc": "Description",
        "col_amount": "Montant ($)",
        "col_cat": "Catégorie",
        "col_score": "Score d'anomalie",
        "no_anomalies": "Aucune anomalie détectée dans la période sélectionnée.",
        "s5_heading": "Transactions",
        "s5_caption": "Les montants positifs sont des revenus ou crédits. Les montants négatifs sont des dépenses ou débits.",
        "no_accounts": "Aucune donnée de compte disponible.",
        "no_transactions": "Aucune transaction ne correspond aux filtres sélectionnés.",
        "no_data": "Aucune donnée disponible.",
    },
}


def load_financial_data(database_url: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx_query = """
    SELECT
        t.transaction_date AS date,
        a.account_name,
        a.owner_name,
        a.account_type,
        a.account_subtype,
        t.description,
        t.amount::double precision AS amount,
        t.category,
        t.outlier_score,
        t.is_outlier
    FROM transactions t
    JOIN accounts a ON t.account_key = a.account_key
    ORDER BY t.transaction_date DESC
    """
    acct_query = """
    SELECT
        account_name,
        owner_name,
        account_type,
        account_subtype,
        COALESCE(balance_available, 0)::double precision AS balance_available,
        COALESCE(balance_current,  0)::double precision AS balance_current,
        COALESCE(balance_limit,    0)::double precision AS balance_limit,
        iso_currency_code
    FROM accounts
    """
    with psycopg.connect(database_url) as conn:
        tx_df = pd.read_sql(tx_query, conn)
        acct_df = pd.read_sql(acct_query, conn)
    return tx_df, acct_df


def _label_subtype(subtype: str | None, lang: str) -> str:
    if not subtype:
        return "Other"
    return _SUBTYPE_LABELS.get(lang, _SUBTYPE_LABELS["en"]).get(
        subtype.lower(), subtype.title()
    )


_PAYMENT_KEYWORDS = r"payment|transfer"


def _classify_tx_type(df: pd.DataFrame) -> pd.Series:
    types = pd.Series("expense", index=df.index)
    types[
        df["account_type"].isin(["depository", "investment"]) & (df["amount"] < 0)
    ] = "income"
    types[(df["account_type"] == "credit") & (df["amount"] < 0)] = "transfer"
    types[
        (df["account_type"] == "depository")
        & (df["amount"] > 0)
        & df["description"].str.contains(_PAYMENT_KEYWORDS, case=False, na=False)
    ] = "transfer"
    return types


def _section_net_worth(
    acct_df: pd.DataFrame, T: dict[str, str], lang: str, selected_owners: list[str]
) -> None:
    st.subheader(T["s1_heading"])
    st.caption(T["s1_caption"])

    if acct_df.empty:
        st.info(T["no_accounts"])
        return

    if selected_owners:
        acct_df = acct_df[acct_df["owner_name"].isin(selected_owners)]

    assets_df = acct_df[
        acct_df["account_type"].isin(["depository", "investment"])
    ].copy()
    credit_df = acct_df[acct_df["account_type"] == "credit"].copy()

    total_assets = assets_df["balance_current"].sum()
    total_liabilities = credit_df["balance_current"].sum()
    net_worth = total_assets - total_liabilities

    m1, m2, m3 = st.columns(3)
    m1.metric(T["metric_net_worth"], f"${net_worth:,.2f}")
    m2.metric(T["metric_assets"], f"${total_assets:,.2f}")
    m3.metric(
        T["metric_liabilities"],
        f"${total_liabilities:,.2f}",
        delta=f"-${total_liabilities:,.2f}",
        delta_color="inverse",
    )

    c1, c2 = st.columns(2)
    with c1:
        if not assets_df.empty:
            assets_df = assets_df.copy()
            assets_df["subtype_label"] = assets_df["account_subtype"].apply(
                lambda s: _label_subtype(s, lang)
            )
            fig = px.pie(
                assets_df,
                values="balance_current",
                names="subtype_label",
                title=T["chart_asset_mix"],
                hole=0.4,
                template="plotly_white",
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        owner_data = []
        for _, row in acct_df.iterrows():
            val = (
                row["balance_current"]
                if row["account_type"] != "credit"
                else -row["balance_current"]
            )
            owner_data.append(
                {
                    "owner": row["owner_name"] or "Unknown",
                    "value": val,
                    "type": row["account_type"],
                }
            )
        owner_df = pd.DataFrame(owner_data)
        fig2 = px.bar(
            owner_df,
            x="owner",
            y="value",
            color="type",
            title=T["chart_owner_balance"],
            labels={"value": T["axis_amount"], "owner": T["axis_holder"]},
            barmode="relative",
            template="plotly_white",
        )
        fig2.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig2, use_container_width=True)

    if not credit_df.empty:
        st.markdown(f"**{T['credit_util_heading']}**")
        st.caption(T["credit_util_caption"])
        for _, row in credit_df.iterrows():
            limit = row["balance_limit"]
            current = row["balance_current"]
            pct = (current / limit) if limit > 0 else 0.0
            label = T["credit_util_label"].format(
                card=row["account_name"], owner=row["owner_name"] or "—", pct=pct * 100
            )
            st.progress(min(pct, 1.0), text=label)
    else:
        st.info(T["no_credit"])


def _build_sidebar_filters(
    df: pd.DataFrame, T: dict[str, str]
) -> tuple[pd.DataFrame, list[str]]:
    st.sidebar.header(T["filters"])

    # Month multiselect
    df = df.copy()
    df["_month_key"] = df["date"].dt.to_period("M").astype(str)
    df["_month_label"] = df["date"].dt.strftime("%B %Y")
    month_options = (
        df[["_month_key", "_month_label"]]
        .drop_duplicates()
        .sort_values("_month_key")["_month_label"]
        .tolist()
    )
    selected_month_labels = st.sidebar.multiselect(
        T["period"], options=month_options, default=month_options
    )
    selected_month_keys = df.loc[
        df["_month_label"].isin(selected_month_labels), "_month_key"
    ].unique()

    # Owner multiselect
    owners = sorted(df["owner_name"].dropna().unique())
    selected_owners = st.sidebar.multiselect(
        T["owners"], options=owners, default=owners
    )

    # Category multiselect
    cats = sorted(df["category"].dropna().unique())
    selected_cats = st.sidebar.multiselect(T["categories"], options=cats, default=cats)

    # Account multiselect — options restricted to the selected owners
    owner_subset = df[df["owner_name"].isin(selected_owners)] if selected_owners else df
    accounts = sorted(owner_subset["account_name"].dropna().unique())
    selected_accounts = st.sidebar.multiselect(
        T["accounts"], options=accounts, default=accounts
    )

    # Amount range slider
    abs_amounts = df["amount"].abs()
    min_amt = float(abs_amounts.min())
    max_amt = float(abs_amounts.max())
    amt_range = st.sidebar.slider(
        T["amount_range"],
        min_value=min_amt,
        max_value=max_amt,
        value=(min_amt, max_amt),
        format="$%.2f",
    )

    # Description search
    search = st.sidebar.text_input(T["search"], value="")

    # Outliers-only toggle
    outliers_only = st.sidebar.toggle(T["outliers_only"], value=False)

    desc_mask = (
        df["description"].str.contains(search, case=False, na=False)
        if search
        else pd.Series(True, index=df.index)
    )
    outlier_mask = df["is_outlier"] if outliers_only else pd.Series(True, index=df.index)

    mask = (
        df["_month_key"].isin(selected_month_keys)
        & df["owner_name"].isin(selected_owners)
        & df["category"].isin(selected_cats)
        & df["account_name"].isin(selected_accounts)
        & (df["amount"].abs() >= amt_range[0])
        & (df["amount"].abs() <= amt_range[1])
        & desc_mask
        & outlier_mask
    )
    return df[mask].drop(columns=["_month_key", "_month_label"]), list(selected_owners)


def _section_cash_flow(df: pd.DataFrame, T: dict[str, str]) -> None:
    st.subheader(T["s3_heading"])
    st.caption(T["s3_caption"])

    df = df.copy()
    df["adjusted_amount"] = -df["amount"]
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["tx_type"] = _classify_tx_type(df)

    real = df[df["tx_type"] != "transfer"]
    income = real[real["tx_type"] == "income"]["adjusted_amount"].sum()
    expenses = real[real["tx_type"] == "expense"]["adjusted_amount"].sum()
    net_flow = income + expenses
    transfer_count = int((df["tx_type"] == "transfer").sum())
    flags = int(df["is_outlier"].sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(T["metric_income"], f"+${income:,.2f}")
    m2.metric(T["metric_expenses"], f"${expenses:,.2f}")
    m3.metric(
        T["metric_net_flow"],
        f"${net_flow:,.2f}",
        delta=f"${net_flow:,.2f}",
        delta_color="normal" if net_flow >= 0 else "inverse",
    )
    m4.metric(T["metric_transfers"], str(transfer_count))
    m5.metric(T["metric_flags"], str(flags))
    st.caption(T["transfers_note"])

    c1, c2 = st.columns(2)
    with c1:
        st.caption(T["burn_caption"])
        spend = (
            real[real["tx_type"] == "expense"]
            .groupby("date", as_index=False)["adjusted_amount"]
            .sum()
            .sort_values("date")
        )
        spend["abs_spend"] = spend["adjusted_amount"].abs()
        spend["rolling_30d"] = spend["abs_spend"].rolling(30, min_periods=1).sum()
        fig = px.line(
            spend,
            x="date",
            y="rolling_30d",
            title=T["chart_burn"],
            labels={"rolling_30d": T["axis_amount"], "date": T["axis_date"]},
            template="plotly_white",
        )
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        split = real.groupby(["month", "owner_name"], as_index=False)[
            "adjusted_amount"
        ].sum()
        fig2 = px.bar(
            split,
            x="month",
            y="adjusted_amount",
            color="owner_name",
            title=T["chart_monthly_net"],
            barmode="group",
            labels={
                "adjusted_amount": T["axis_amount"],
                "month": T["axis_month"],
                "owner_name": T["axis_holder"],
            },
            template="plotly_white",
        )
        fig2.add_hline(y=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig2, use_container_width=True)

    exp_only = real[real["tx_type"] == "expense"].copy()
    exp_only["abs_amount"] = exp_only["adjusted_amount"].abs()
    dist = exp_only.groupby(["month", "category"], as_index=False)["abs_amount"].sum()
    fig3 = px.bar(
        dist,
        x="month",
        y="abs_amount",
        color="category",
        title=T["chart_cat_dist"],
        labels={"abs_amount": T["axis_amount"], "month": T["axis_month"]},
        template="plotly_white",
    )
    st.plotly_chart(fig3, use_container_width=True)

    return df


def _section_anomalies(df: pd.DataFrame, T: dict[str, str]) -> None:
    st.subheader(T["s4_heading"])
    st.caption(T["s4_caption"])

    outliers = df[df["is_outlier"]].copy()

    if outliers.empty:
        st.info(T["no_anomalies"])
        return

    outliers["abs_amount"] = outliers["adjusted_amount"].abs()
    fig = px.scatter(
        outliers,
        x="date",
        y="outlier_score",
        color="category",
        size="abs_amount",
        hover_data=["description", "adjusted_amount", "owner_name"],
        title=T["chart_outlier_scatter"],
        labels={"outlier_score": T["axis_score"], "date": T["axis_date"]},
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    display = outliers[
        [
            "date",
            "owner_name",
            "account_name",
            "description",
            "adjusted_amount",
            "category",
            "outlier_score",
        ]
    ].copy()
    display.columns = [
        T["col_date"],
        T["col_owner"],
        T["col_account"],
        T["col_desc"],
        T["col_amount"],
        T["col_cat"],
        T["col_score"],
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)


def _section_ledger(df: pd.DataFrame, T: dict[str, str]) -> None:
    st.subheader(T["s5_heading"])
    st.caption(T["s5_caption"])

    display = df[
        [
            "date",
            "owner_name",
            "account_name",
            "description",
            "adjusted_amount",
            "category",
        ]
    ].copy()
    display.columns = [
        T["col_date"],
        T["col_owner"],
        T["col_account"],
        T["col_desc"],
        T["col_amount"],
        T["col_cat"],
    ]
    st.dataframe(display, use_container_width=True, hide_index=True)


def render_dashboard(tx_df: pd.DataFrame, acct_df: pd.DataFrame) -> None:
    def _on_lang_toggle() -> None:
        st.session_state["lang"] = "fr" if st.session_state.get("lang_fr") else "en"

    st.sidebar.toggle(
        "Français",
        key="lang_fr",
        value=st.session_state.get("lang", "en") == "fr",
        on_change=_on_lang_toggle,
    )
    st.sidebar.divider()

    lang = st.session_state.get("lang", "en")
    T = _STRINGS[lang]

    st.title(T["title"])

    if tx_df.empty and acct_df.empty:
        st.info(T["no_data"])
        return

    if tx_df.empty:
        st.info(T["no_transactions"])
        _section_net_worth(acct_df, T, lang, [])
        return

    tx = tx_df.copy()
    tx["date"] = pd.to_datetime(tx["date"])

    filtered, selected_owners = _build_sidebar_filters(tx, T)

    _section_net_worth(acct_df, T, lang, selected_owners)
    st.divider()

    if filtered.empty:
        st.info(T["no_transactions"])
        return

    st.divider()
    enriched = _section_cash_flow(filtered, T)
    st.divider()
    _section_anomalies(enriched, T)
    st.divider()
    _section_ledger(enriched, T)
