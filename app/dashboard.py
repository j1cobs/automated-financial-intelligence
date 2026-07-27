from __future__ import annotations

import calendar
from datetime import date

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st

from database.db import DatabaseClient

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
        "duplicates_only": "Possible duplicates only",
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
        "credit_util_label": "{card} — {owner} — ${current:,.2f} / ${limit:,.2f} ({pct:.0f}% used)",
        "credit_util_label_manual": "{card} — {owner} — ${current:,.2f} / ${limit:,.2f} ({pct:.0f}% used, manual limit)",
        "credit_util_unknown": "{card} — {owner} — ${current:,.2f} owed — no credit limit set",
        "no_credit": "No credit accounts found.",
        "stale_balances": "Balances may be out of date for: {accounts}. Re-run the pipeline or repair the Plaid connection.",
        "account_fork": "Possible duplicate account(s) detected: {accounts}. Run scripts/dedupe_accounts.py to merge their history.",
        "credit_limit_editor_heading": "Set credit limits",
        "col_card": "Card",
        "col_owner": "Owner",
        "col_plaid_limit": "Plaid limit",
        "col_manual_limit": "Your limit",
        "credit_limit_save": "Save limits",
        "credit_limit_saved": "Credit limits saved.",
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
        "col_account": "Account",
        "col_desc": "Description",
        "col_amount": "Amount ($)",
        "col_cat": "Category",
        "col_recurring": "Recurring",
        "col_duplicate": "Duplicate",
        "col_score": "Outlier score",
        "no_anomalies": "No anomalies detected in the selected period.",
        # Section 5
        "s5_heading": "Transactions",
        "s5_caption": "Positive amounts are income or credits. Negative amounts are expenses or debits.",
        "s5_duplicate_caption": (
            "Tick Duplicate to exclude a double-posted transaction from every total and chart. "
            "Flagged rows stay listed here so you can untick them."
        ),
        # Empty states
        "no_accounts": "No account data available.",
        "no_transactions": "No transactions match the selected filters.",
        "no_data": "No data available.",
        # Tabs
        "tab_overview": "Overview",
        "tab_cashflow": "Cash flow",
        "tab_budget": "Budget",
        "tab_transactions": "Transactions",
        # Overview section
        "s0_heading": "Summary",
        "metric_savings_rate": "Savings rate",
        "chart_top_categories": "Top spending categories",
        "chart_mom_comparison": "Month-over-month by category",
        "label_this_month": "This month",
        "label_last_month": "Last month",
        "chart_income_breakdown": "Income sources",
        "chart_savings_rate_trend": "Monthly savings rate (%)",
        "metric_emergency_fund": "Emergency fund coverage",
        "emergency_fund_months": "{months:.1f} months of expenses covered",
        "emergency_fund_note": "Liquid savings ÷ average monthly expenses.",
        # Budget section
        "s_budget_heading": "Budget",
        "s_budget_caption": "Monthly spending limits by category.",
        "budget_col_category": "Category",
        "budget_col_limit": "Limit ($)",
        "budget_col_spent": "Spent",
        "budget_col_projected": "Projected EOM",
        "budget_col_actual": "Actual",
        "budget_edit_label": "Edit budget limits",
        "budget_save": "Save budgets",
        "budget_saved": "Budgets saved.",
        "budget_over": "Over budget",
        "budget_on_track": "On track",
        "budget_current_month_note": (
            "Budget view follows your period filter. Projection only shown for current month."
        ),
        # Cash flow additions
        "chart_mom_bar": "Income vs. expenses by month",
        "chart_savings_rate": "Monthly savings rate (%)",
        # Transactions tab
        "edit_cat_label": "Edit categories inline — changes persist across pipeline re-runs.",
        # Quick-range period filter
        "period_range": "Period",
        "period_last_30_days": "Last 30 days",
        "period_current_month": "Current month",
        "period_last_3_months": "Last 3 months",
        "period_last_6_months": "Last 6 months",
        "period_ytd": "Year to date",
        "period_all_time": "All time",
        "period_custom": "Custom",
        # Weekly metrics
        "metric_avg_weekly_spend": "Avg. weekly spend",
        "metric_avg_monthly_spend": "Avg. monthly spend",
        "metric_avg_weekly_income": "Avg. weekly income",
        "metric_avg_monthly_income": "Avg. monthly income",
        "chart_weekly_trend": "Income vs. expenses by week",
        "axis_week": "Week",
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
        "duplicates_only": "Doublons possibles uniquement",
        "s1_heading": "Aperçu de la valeur nette",
        "s1_caption": "Total des actifs moins le total des dettes.",
        "metric_net_worth": "Valeur nette",
        "metric_assets": "Total des actifs",
        "metric_liabilities": "Total des passifs",
        "chart_asset_mix": "Répartition des actifs par type de compte",
        "chart_owner_balance": "Actifs vs. passifs par titulaire",
        "credit_util_heading": "Utilisation des cartes de crédit",
        "credit_util_caption": "Limite de crédit utilisée par carte.",
        "credit_util_label": "{card} — {owner} — {current:,.2f} $ / {limit:,.2f} $ ({pct:.0f} % utilisé)",
        "credit_util_label_manual": "{card} — {owner} — {current:,.2f} $ / {limit:,.2f} $ ({pct:.0f} % utilisé, limite manuelle)",
        "credit_util_unknown": "{card} — {owner} — {current:,.2f} $ dus — aucune limite de crédit définie",
        "no_credit": "Aucun compte de crédit trouvé.",
        "stale_balances": "Les soldes pourraient être désuets pour : {accounts}. Relancez le pipeline ou réparez la connexion Plaid.",
        "account_fork": "Compte(s) possiblement en double détecté(s) : {accounts}. Exécutez scripts/dedupe_accounts.py pour fusionner leur historique.",
        "credit_limit_editor_heading": "Définir les limites de crédit",
        "col_card": "Carte",
        "col_owner": "Titulaire",
        "col_plaid_limit": "Limite Plaid",
        "col_manual_limit": "Votre limite",
        "credit_limit_save": "Enregistrer les limites",
        "credit_limit_saved": "Limites de crédit enregistrées.",
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
        "col_account": "Compte",
        "col_desc": "Description",
        "col_amount": "Montant ($)",
        "col_cat": "Catégorie",
        "col_recurring": "Récurrent",
        "col_duplicate": "Doublon",
        "col_score": "Score d'anomalie",
        "no_anomalies": "Aucune anomalie détectée dans la période sélectionnée.",
        "s5_heading": "Transactions",
        "s5_caption": (
            "Les montants positifs sont des revenus ou crédits. "
            "Les montants négatifs sont des dépenses ou débits."
        ),
        "s5_duplicate_caption": (
            "Cochez Doublon pour exclure une transaction publiée en double de tous les totaux et "
            "graphiques. Les lignes signalées restent affichées ici pour pouvoir être décochées."
        ),
        "no_accounts": "Aucune donnée de compte disponible.",
        "no_transactions": "Aucune transaction ne correspond aux filtres sélectionnés.",
        "no_data": "Aucune donnée disponible.",
        "tab_overview": "Aperçu",
        "tab_cashflow": "Flux monétaires",
        "tab_budget": "Budget",
        "tab_transactions": "Transactions",
        "s0_heading": "Résumé",
        "metric_savings_rate": "Taux d'épargne",
        "chart_top_categories": "Principales catégories de dépenses",
        "chart_mom_comparison": "Comparaison mois par mois par catégorie",
        "label_this_month": "Ce mois",
        "label_last_month": "Mois dernier",
        "chart_income_breakdown": "Sources de revenus",
        "chart_savings_rate_trend": "Taux d'épargne mensuel (%)",
        "metric_emergency_fund": "Fonds d'urgence",
        "emergency_fund_months": "{months:.1f} mois de dépenses couverts",
        "emergency_fund_note": "Épargne liquide ÷ dépenses mensuelles moyennes.",
        "s_budget_heading": "Budget",
        "s_budget_caption": "Limites de dépenses mensuelles par catégorie.",
        "budget_col_category": "Catégorie",
        "budget_col_limit": "Limite ($)",
        "budget_col_spent": "Dépensé",
        "budget_col_projected": "Prévision fin de mois",
        "budget_col_actual": "Réel final",
        "budget_edit_label": "Modifier les limites budgétaires",
        "budget_save": "Enregistrer",
        "budget_saved": "Budgets enregistrés.",
        "budget_over": "Dépassé",
        "budget_on_track": "Dans les limites",
        "budget_current_month_note": (
            "La vue budget suit le filtre de période. La projection n'est affichée que pour le mois en cours."
        ),
        "chart_mom_bar": "Revenus vs. dépenses par mois",
        "chart_savings_rate": "Taux d'épargne mensuel (%)",
        "edit_cat_label": (
            "Modifiez les catégories en ligne — les changements survivent aux ré-exécutions du pipeline."
        ),
        "period_range": "Période",
        "period_last_30_days": "30 derniers jours",
        "period_current_month": "Mois en cours",
        "period_last_3_months": "3 derniers mois",
        "period_last_6_months": "6 derniers mois",
        "period_ytd": "Depuis le début de l'année",
        "period_all_time": "Depuis toujours",
        "period_custom": "Personnalisé",
        "metric_avg_weekly_spend": "Dépense moy. hebdo",
        "metric_avg_monthly_spend": "Dépense moy. mensuelle",
        "metric_avg_weekly_income": "Revenu moy. hebdo",
        "metric_avg_monthly_income": "Revenu moy. mensuel",
        "chart_weekly_trend": "Revenus vs. dépenses par semaine",
        "axis_week": "Semaine",
    },
}


def load_financial_data(database_url: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx_query = """
    SELECT
        t.transaction_date   AS date,
        t.transaction_hash,
        t.account_key,
        a.account_name,
        a.owner_name,
        a.account_type,
        a.account_subtype,
        t.description,
        t.amount::double precision AS amount,
        COALESCE(t.user_category, t.category) AS category,
        t.outlier_score,
        t.is_outlier,
        t.is_recurring,
        t.is_duplicate
    FROM transactions t
    JOIN accounts a ON t.account_key = a.account_key
    ORDER BY t.transaction_date DESC
    """
    acct_query = """
    SELECT
        account_key,
        account_name,
        official_name,
        mask,
        owner_name,
        account_type,
        account_subtype,
        COALESCE(balance_available, 0)::double precision AS balance_available,
        COALESCE(balance_current,  0)::double precision AS balance_current,
        balance_limit::double precision AS balance_limit,
        manual_credit_limit::double precision AS manual_credit_limit,
        iso_currency_code,
        updated_at
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


_PAYMENT_KEYWORDS = r"payment|paiement|prélèvement|prelevement|transfer|xfer"
_REFUND_KEYWORDS = r"cashback|cash.?back|remise|refund|rebate|return"
_TRANSFER_MATCH_DAYS = 5


def _detect_internal_transfers(df: pd.DataFrame) -> pd.Series:
    """Flag both legs of a transfer between two of the user's own accounts.

    A pair is an outflow (amount > 0) and an inflow (amount < 0) of the same
    magnitude, on two *different* accounts, within _TRANSFER_MATCH_DAYS days.
    Matching is greedy and one-to-one: each row can be consumed by one pair only,
    so three $500 outflows never mark the same $500 inflow three times.

    Money arriving with no matching outgoing leg in the data is left unflagged —
    an inbound e-transfer from another person is income, not a transfer.
    """
    is_paired = pd.Series(False, index=df.index)
    if df.empty:
        return is_paired

    abs_amount = df["amount"].abs().round(2)
    for _, bucket in df.groupby(abs_amount).groups.items():
        bucket_idx = list(bucket)
        if len(bucket_idx) < 2:
            continue
        outflows = [i for i in bucket_idx if df.loc[i, "amount"] > 0]
        inflows = [i for i in bucket_idx if df.loc[i, "amount"] < 0]
        if not outflows or not inflows:
            continue
        unmatched_inflows = set(inflows)
        outflows_sorted = sorted(outflows, key=lambda i: df.loc[i, "date"])
        for out_idx in outflows_sorted:
            out_date = df.loc[out_idx, "date"]
            out_account = df.loc[out_idx, "account_name"]
            candidates = [
                in_idx
                for in_idx in unmatched_inflows
                if df.loc[in_idx, "account_name"] != out_account
                and abs((df.loc[in_idx, "date"] - out_date).days)
                <= _TRANSFER_MATCH_DAYS
            ]
            if not candidates:
                continue
            best = min(
                candidates, key=lambda i: abs((df.loc[i, "date"] - out_date).days)
            )
            unmatched_inflows.discard(best)
            is_paired.loc[out_idx] = True
            is_paired.loc[best] = True

    return is_paired


def _classify_tx_type(df: pd.DataFrame) -> pd.Series:
    """Classify each row as 'income', 'expense', or 'transfer'.

    Sign convention (Plaid): positive amount = outflow; negative = inflow.
    adjusted_amount = -amount, so positive adjusted_amount = income/gain.

    Invariant: no row on a credit account is ever classified 'income' — a
    credit-account inflow is either a refund (netted against expense) or a
    card payment (transfer), never new money. Internal transfers between the
    user's own accounts (matched pairs via _detect_internal_transfers) are
    excluded from both income and expense on both legs; unpaired inflows on
    depository/investment accounts stay 'income' since they may be money from
    someone else (e.g. an incoming e-transfer), which keyword matching alone
    cannot distinguish from an internal transfer.
    """
    types = pd.Series("expense", index=df.index)

    is_depository_or_investment = df["account_type"].isin(["depository", "investment"])
    is_credit = df["account_type"] == "credit"
    is_unknown = ~is_depository_or_investment & ~is_credit  # NULL or unrecognized

    # Depository / investment: negative amount = money arriving = income
    types[is_depository_or_investment & (df["amount"] < 0)] = "income"
    # Depository / investment: positive amount with payment keyword = transfer
    types[
        is_depository_or_investment
        & (df["amount"] > 0)
        & df["description"].str.contains(_PAYMENT_KEYWORDS, case=False, na=False)
    ] = "transfer"

    # Credit card: positive = purchase = expense (default already set)
    # Credit card: negative + refund keyword = reversal of a purchase = expense (nets against spend)
    types[
        is_credit
        & (df["amount"] < 0)
        & df["description"].str.contains(_REFUND_KEYWORDS, case=False, na=False)
    ] = "expense"
    # Credit card: negative without refund keyword = payment received = transfer
    types[
        is_credit
        & (df["amount"] < 0)
        & ~df["description"].str.contains(_REFUND_KEYWORDS, case=False, na=False)
    ] = "transfer"

    # Unknown account_type: treat negative amounts as income (conservative fallback)
    types[is_unknown & (df["amount"] < 0)] = "income"

    # Internal transfers (matched pairs across the user's own accounts) override
    # everything above — applied last so a paired inflow flips from income/expense
    # to transfer on both legs.
    types[_detect_internal_transfers(df)] = "transfer"

    return types


def _enrich_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Add adjusted_amount, month, week, and tx_type columns. Call once before tabs."""
    df = df.copy()
    df["adjusted_amount"] = -df["amount"]
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["week"] = df["date"].dt.to_period("W-SUN").astype(str)
    df["tx_type"] = _classify_tx_type(df)
    return df


def _effective_credit_limit(
    balance_limit: float, manual_credit_limit: float
) -> tuple[float | None, bool]:
    """Resolve the credit limit to use for utilisation: Plaid's value if present,
    otherwise the manually-entered fallback. Returns (limit, is_manual); limit is
    None when neither source has a value."""
    if pd.notna(balance_limit) and balance_limit > 0:
        return balance_limit, False
    if pd.notna(manual_credit_limit) and manual_credit_limit > 0:
        return manual_credit_limit, True
    return None, False


_STALE_BALANCE_DAYS = 3


def _section_net_worth(
    acct_df: pd.DataFrame,
    T: dict[str, str],
    lang: str,
    selected_owners: list[str],
    database_url: str,
) -> None:
    st.subheader(T["s1_heading"])
    st.caption(T["s1_caption"])

    if acct_df.empty:
        st.info(T["no_accounts"])
        return

    all_acct_df = acct_df  # unfiltered — the credit limit editor must not hide any card

    if selected_owners:
        acct_df = acct_df[acct_df["owner_name"].isin(selected_owners)]

    assets_df = acct_df[
        acct_df["account_type"].isin(["depository", "investment"])
    ].copy()
    credit_df = acct_df[acct_df["account_type"] == "credit"].copy()

    stale_cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=_STALE_BALANCE_DAYS)
    stale_df = all_acct_df[
        pd.to_datetime(all_acct_df["updated_at"], utc=True) < stale_cutoff
    ]
    if not stale_df.empty:
        stale_names = ", ".join(
            f"{row['account_name']} ({(pd.Timestamp.now(tz='UTC') - pd.to_datetime(row['updated_at'], utc=True)).days}d)"
            for _, row in stale_df.iterrows()
        )
        st.warning(T["stale_balances"].format(accounts=stale_names))

    identity_cols = ["official_name", "account_subtype", "account_type", "mask"]
    identifiable = all_acct_df.dropna(subset=identity_cols)
    fork_sizes = identifiable.groupby(identity_cols)["account_key"].transform("size")
    forked_df = identifiable[fork_sizes > 1]
    if not forked_df.empty:
        forked_names = ", ".join(sorted(forked_df["account_name"].unique()))
        st.warning(T["account_fork"].format(accounts=forked_names))

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
            current = row["balance_current"]
            limit, is_manual = _effective_credit_limit(
                row["balance_limit"], row["manual_credit_limit"]
            )
            owner = row["owner_name"] or "—"
            if limit is None:
                st.write(
                    T["credit_util_unknown"].format(
                        card=row["account_name"], owner=owner, current=current
                    )
                )
                continue
            pct = current / limit
            key = "credit_util_label_manual" if is_manual else "credit_util_label"
            label = T[key].format(
                card=row["account_name"],
                owner=owner,
                current=current,
                limit=limit,
                pct=pct * 100,
            )
            st.progress(min(max(pct, 0.0), 1.0), text=label)
    else:
        st.info(T["no_credit"])

    all_credit_df = all_acct_df[all_acct_df["account_type"] == "credit"]
    if not all_credit_df.empty:
        with st.expander(T["credit_limit_editor_heading"]):
            editor_df = pd.DataFrame(
                [
                    {
                        "account_key": row["account_key"],
                        T["col_card"]: row["account_name"],
                        T["col_owner"]: row["owner_name"] or "—",
                        T["col_plaid_limit"]: (
                            row["balance_limit"]
                            if pd.notna(row["balance_limit"])
                            else None
                        ),
                        T["col_manual_limit"]: (
                            row["manual_credit_limit"]
                            if pd.notna(row["manual_credit_limit"])
                            else None
                        ),
                    }
                    for _, row in all_credit_df.iterrows()
                ]
            )
            edited = st.data_editor(
                editor_df.drop(columns=["account_key"]),
                key="credit_limit_editor",
                column_config={
                    T["col_card"]: st.column_config.TextColumn(disabled=True),
                    T["col_owner"]: st.column_config.TextColumn(disabled=True),
                    T["col_plaid_limit"]: st.column_config.NumberColumn(
                        disabled=True, format="$%.2f"
                    ),
                    T["col_manual_limit"]: st.column_config.NumberColumn(
                        min_value=0, format="$%.2f"
                    ),
                },
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
            )
            if st.button(T["credit_limit_save"]):
                db = DatabaseClient(database_url)
                for i, row in edited.iterrows():
                    account_key = editor_df.iloc[i]["account_key"]
                    new_limit = row[T["col_manual_limit"]]
                    db.set_manual_credit_limit(
                        str(account_key),
                        float(new_limit) if pd.notna(new_limit) else None,
                    )
                st.success(T["credit_limit_saved"])
                st.rerun()


_PERIOD_PRESETS = [
    "last_30_days",
    "current_month",
    "last_3_months",
    "last_6_months",
    "ytd",
    "all_time",
    "custom",
]


def _preset_month_keys(preset: str, df: pd.DataFrame) -> pd.Index:
    """Month keys touched by a quick-range preset, anchored to the latest transaction date."""
    max_date = df["date"].max()
    if preset == "all_time":
        return df["_month_key"].unique()
    if preset == "last_30_days":
        start = max_date - pd.Timedelta(days=29)
    elif preset == "current_month":
        start = max_date.replace(day=1)
    elif preset == "last_3_months":
        start = max_date - pd.DateOffset(months=3)
    elif preset == "last_6_months":
        start = max_date - pd.DateOffset(months=6)
    elif preset == "ytd":
        start = max_date.replace(month=1, day=1)
    else:
        start = df["date"].min()
    window_mask = (df["date"] >= start) & (df["date"] <= max_date)
    return df.loc[window_mask, "_month_key"].unique()


def _build_sidebar_filters(
    df: pd.DataFrame, T: dict[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    st.sidebar.header(T["filters"])

    # Month bookkeeping (shared by the quick-range presets and the custom multiselect)
    df = df.copy()
    df["_month_key"] = df["date"].dt.to_period("M").astype(str)
    df["_month_label"] = df["date"].dt.strftime("%B %Y")
    month_options = (
        df[["_month_key", "_month_label"]]
        .drop_duplicates()
        .sort_values("_month_key")["_month_label"]
        .tolist()
    )

    # Quick-range period selector
    selected_preset = st.sidebar.selectbox(
        T["period_range"],
        options=_PERIOD_PRESETS,
        format_func=lambda key: T[f"period_{key}"],
        index=0,
    )
    if selected_preset == "custom":
        selected_month_labels = st.sidebar.multiselect(
            T["period"], options=month_options, default=month_options
        )
        selected_month_keys = df.loc[
            df["_month_label"].isin(selected_month_labels), "_month_key"
        ].unique()
    else:
        selected_month_keys = _preset_month_keys(selected_preset, df)

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

    # Duplicates-only toggle — narrows the view to rows that share
    # (account_key, date, description, amount) with at least one other row, i.e. the
    # candidates the user has to inspect by hand. Grouping on account_key rather than
    # account_name avoids collapsing two distinct accounts with the same display name.
    duplicates_only = st.sidebar.toggle(T["duplicates_only"], value=False)

    desc_mask = (
        df["description"].str.contains(search, case=False, na=False)
        if search
        else pd.Series(True, index=df.index)
    )
    outlier_mask = (
        df["is_outlier"] if outliers_only else pd.Series(True, index=df.index)
    )
    if duplicates_only:
        group_sizes = df.groupby(
            ["account_key", "date", "description", "amount"], dropna=False
        )["amount"].transform("size")
        duplicate_mask = group_sizes > 1
    else:
        duplicate_mask = pd.Series(True, index=df.index)

    non_date_mask = (
        df["owner_name"].isin(selected_owners)
        & df["category"].isin(selected_cats)
        & df["account_name"].isin(selected_accounts)
        & (df["amount"].abs() >= amt_range[0])
        & (df["amount"].abs() <= amt_range[1])
        & desc_mask
        & outlier_mask
        & duplicate_mask
    )
    date_mask = df["_month_key"].isin(selected_month_keys)

    return (
        df[non_date_mask & date_mask].drop(columns=["_month_key", "_month_label"]),
        df[non_date_mask].drop(columns=["_month_key", "_month_label"]),
        list(selected_owners),
    )


def _section_overview(
    df: pd.DataFrame,
    all_time_df: pd.DataFrame,
    acct_df: pd.DataFrame,
    T: dict[str, str],
    lang: str,
    selected_owners: list[str],
) -> None:
    st.subheader(T["s0_heading"])

    real = df[df["tx_type"] != "transfer"]
    income = real[real["tx_type"] == "income"]["adjusted_amount"].sum()
    expenses = abs(real[real["tx_type"] == "expense"]["adjusted_amount"].sum())
    net_flow = income - expenses
    savings_rate = (net_flow / income * 100) if income > 0 else 0.0
    flagged = int(df["is_outlier"].sum())

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(T["metric_income"], f"+${income:,.2f}")
    m2.metric(T["metric_expenses"], f"-${expenses:,.2f}")
    m3.metric(
        T["metric_net_flow"],
        f"${net_flow:,.2f}",
        delta=f"${net_flow:,.2f}",
        delta_color="normal" if net_flow >= 0 else "inverse",
    )
    m4.metric(T["metric_savings_rate"], f"{savings_rate:.1f}%")
    m5.metric(T["metric_flags"], str(flagged))

    # Weekly vs. monthly average pace — zero-filled so inactive weeks/months pull the average down
    weekly_totals = (
        real.groupby(["week", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0)
    )
    monthly_totals = (
        real.groupby(["month", "tx_type"])["adjusted_amount"]
        .sum()
        .unstack(fill_value=0)
    )

    avg_weekly_expense = (
        weekly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0
    )
    avg_monthly_expense = (
        monthly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0
    )
    avg_weekly_income = (
        weekly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0
    )
    avg_monthly_income = (
        monthly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0
    )

    w1, w2, w3, w4 = st.columns(4)
    w1.metric(T["metric_avg_weekly_spend"], f"${avg_weekly_expense:,.2f}")
    w2.metric(T["metric_avg_monthly_spend"], f"${avg_monthly_expense:,.2f}")
    w3.metric(T["metric_avg_weekly_income"], f"${avg_weekly_income:,.2f}")
    w4.metric(T["metric_avg_monthly_income"], f"${avg_monthly_income:,.2f}")

    # Comparison-shaped charts: bounded to the trailing 12 months of all-time data,
    # not the sidebar's quick-range window — otherwise they'd dilute/go stale over the years.
    at_max_date = all_time_df["date"].max()
    bounded_all_time = all_time_df[
        all_time_df["date"] >= at_max_date - pd.DateOffset(months=12)
    ]

    c1, c2 = st.columns(2)
    with c1:
        top_cats = (
            bounded_all_time[bounded_all_time["tx_type"] == "expense"]
            .groupby("category", as_index=False)["adjusted_amount"]
            .sum()
            .assign(abs_amount=lambda x: x["adjusted_amount"].abs())
            .nlargest(10, "abs_amount")
            .sort_values("abs_amount")
        )
        if not top_cats.empty:
            fig = px.bar(
                top_cats,
                x="abs_amount",
                y="category",
                orientation="h",
                title=T["chart_top_categories"],
                labels={"abs_amount": T["axis_amount"], "category": T["col_cat"]},
                template="plotly_white",
            )
            st.plotly_chart(fig, use_container_width=True)

    with c2:
        months_sorted = sorted(bounded_all_time["month"].unique())
        if len(months_sorted) >= 2:
            this_m, last_m = months_sorted[-1], months_sorted[-2]
            mom = bounded_all_time[
                bounded_all_time["month"].isin([this_m, last_m])
                & (bounded_all_time["tx_type"] == "expense")
            ]
            mom_grp = mom.groupby(["category", "month"], as_index=False)[
                "adjusted_amount"
            ].sum()
            mom_grp["abs_amount"] = mom_grp["adjusted_amount"].abs()
            mom_grp["period"] = mom_grp["month"].map(
                {this_m: T["label_this_month"], last_m: T["label_last_month"]}
            )
            fig2 = px.bar(
                mom_grp,
                x="category",
                y="abs_amount",
                color="period",
                barmode="group",
                title=T["chart_mom_comparison"],
                template="plotly_white",
            )
            st.plotly_chart(fig2, use_container_width=True)

    owner_mask = (
        acct_df["owner_name"].isin(selected_owners)
        if selected_owners
        else pd.Series(True, index=acct_df.index)
    )
    liquid_assets = acct_df[acct_df["account_type"].isin(["depository"]) & owner_mask][
        "balance_current"
    ].sum()

    # Trend-shaped: always full history, ignoring the sidebar's quick-range window.
    monthly_expenses_series = (
        all_time_df[all_time_df["tx_type"] == "expense"]
        .groupby("month")["adjusted_amount"]
        .sum()
        .abs()
    )
    if not monthly_expenses_series.empty:
        avg_monthly_expenses = monthly_expenses_series.mean()
        if avg_monthly_expenses > 0:
            months_covered = liquid_assets / avg_monthly_expenses
            st.metric(
                T["metric_emergency_fund"],
                T["emergency_fund_months"].format(months=months_covered),
            )
            st.caption(T["emergency_fund_note"])
            st.progress(min(months_covered / 6, 1.0))

    c3, c4 = st.columns(2)
    with c3:
        income_src = (
            df[df["tx_type"] == "income"]
            .groupby("description", as_index=False)["adjusted_amount"]
            .sum()
            .nlargest(8, "adjusted_amount")
        )
        if not income_src.empty:
            fig_inc = px.pie(
                income_src,
                values="adjusted_amount",
                names="description",
                title=T["chart_income_breakdown"],
                hole=0.35,
                template="plotly_white",
            )
            st.plotly_chart(fig_inc, use_container_width=True)

    with c4:
        monthly = (
            all_time_df[all_time_df["tx_type"] != "transfer"]
            .groupby("month")
            .apply(
                lambda g: pd.Series(
                    {
                        "income": g.loc[
                            g["tx_type"] == "income", "adjusted_amount"
                        ].sum(),
                        "expenses": abs(
                            g.loc[g["tx_type"] == "expense", "adjusted_amount"].sum()
                        ),
                    }
                )
            )
            .reset_index()
        )
        if not monthly.empty:
            monthly["savings_rate"] = (
                (monthly["income"] - monthly["expenses"])
                / monthly["income"].clip(lower=0.01)
                * 100
            )
            fig_sr = px.line(
                monthly,
                x="month",
                y="savings_rate",
                title=T["chart_savings_rate_trend"],
                labels={"savings_rate": "%", "month": T["axis_month"]},
                template="plotly_white",
            )
            fig_sr.add_hline(
                y=20, line_dash="dot", line_color="green", annotation_text="Target 20%"
            )
            st.plotly_chart(fig_sr, use_container_width=True)


def _section_cash_flow(df: pd.DataFrame, T: dict[str, str]) -> None:
    st.subheader(T["s3_heading"])
    st.caption(T["s3_caption"])

    df = df.copy()

    real = df[df["tx_type"] != "transfer"]
    income = real[real["tx_type"] == "income"]["adjusted_amount"].sum()
    expenses = real[real["tx_type"] == "expense"]["adjusted_amount"].sum()
    net_flow = income + expenses
    transfer_count = int((df["tx_type"] == "transfer").sum())
    flags = int(df["is_outlier"].sum())
    savings_rate = (net_flow / income * 100) if income > 0 else 0.0

    m1, m2, m3, m4, m5, m6 = st.columns(6)
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
    m6.metric(T["metric_savings_rate"], f"{savings_rate:.1f}%")
    st.caption(T["transfers_note"])

    mom_summary = (
        df[df["tx_type"] != "transfer"]
        .groupby(["month", "tx_type"], as_index=False)["adjusted_amount"]
        .sum()
    )
    mom_summary.loc[mom_summary["tx_type"] == "expense", "adjusted_amount"] = (
        mom_summary.loc[mom_summary["tx_type"] == "expense", "adjusted_amount"].abs()
    )
    fig_mom = px.bar(
        mom_summary,
        x="month",
        y="adjusted_amount",
        color="tx_type",
        barmode="group",
        title=T["chart_mom_bar"],
        template="plotly_white",
        labels={"adjusted_amount": T["axis_amount"], "month": T["axis_month"]},
    )
    st.plotly_chart(fig_mom, use_container_width=True)

    week_summary = (
        df[df["tx_type"] != "transfer"]
        .groupby(["week", "tx_type"], as_index=False)["adjusted_amount"]
        .sum()
    )
    week_summary.loc[week_summary["tx_type"] == "expense", "adjusted_amount"] = (
        week_summary.loc[week_summary["tx_type"] == "expense", "adjusted_amount"].abs()
    )
    fig_week = px.bar(
        week_summary,
        x="week",
        y="adjusted_amount",
        color="tx_type",
        barmode="group",
        title=T["chart_weekly_trend"],
        template="plotly_white",
        labels={"adjusted_amount": T["axis_amount"], "week": T["axis_week"]},
    )
    st.plotly_chart(fig_week, use_container_width=True)

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


def _section_budget(df: pd.DataFrame, T: dict[str, str], database_url: str) -> None:
    st.subheader(T["s_budget_heading"])
    st.caption(T["s_budget_caption"])
    st.caption(T["budget_current_month_note"])

    db = DatabaseClient(database_url)
    budget_rows = db.get_budgets()
    budget_map = {r["category"]: r["monthly_limit"] for r in budget_rows}

    # Determine the period in the filtered data
    current_month_str = df["month"].max()  # e.g. "2025-03"
    today = date.today()
    today_month_str = today.strftime("%Y-%m")
    is_current_month = current_month_str == today_month_str

    # Compute spending for the selected period
    period_expenses = (
        df[(df["month"] == current_month_str) & (df["tx_type"] == "expense")]
        .groupby("category")["adjusted_amount"]
        .sum()
        .abs()
        .to_dict()
    )

    # Projection factor — only meaningful for the current calendar month
    if is_current_month:
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_elapsed = max(today.day, 1)
        projection_factor = days_in_month / days_elapsed
    else:
        projection_factor = None  # historical — show actual, not projection

    # Categories to show: any category with spending OR with a budget set
    all_categories = sorted(set(period_expenses.keys()) | set(budget_map.keys()))

    for cat in all_categories:
        spent = period_expenses.get(cat, 0.0)
        limit = budget_map.get(cat)

        if is_current_month and projection_factor is not None:
            projected_label = f"Projected EOM: ${spent * projection_factor:,.2f}"
        else:
            projected_label = f"Actual: ${spent:,.2f}"

        if limit:
            pct = min(spent / limit, 1.0)
            status = T["budget_over"] if spent > limit else T["budget_on_track"]
            label = f"{cat} — ${spent:,.2f} / ${limit:,.2f} ({pct * 100:.0f}%) — {status} | {projected_label}"
            st.progress(pct, text=label)
        else:
            st.write(
                f"**{cat}**: ${spent:,.2f} spent (no budget set) | {projected_label}"
            )

    st.divider()
    st.markdown(f"**{T['budget_edit_label']}**")

    # Budget editor — all canonical categories from DB
    all_edit_cats = db.get_categories()
    editor_df = pd.DataFrame(
        [
            {"category": cat, "monthly_limit": budget_map.get(cat, 0.0)}
            for cat in all_edit_cats
        ]
    )
    edited = st.data_editor(
        editor_df,
        key="budget_editor",
        column_config={
            "category": st.column_config.TextColumn(
                T["budget_col_category"], disabled=True
            ),
            "monthly_limit": st.column_config.NumberColumn(
                T["budget_col_limit"], min_value=0, format="$%.2f"
            ),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
    )
    if st.button(T["budget_save"]):
        for _, row in edited.iterrows():
            if row["monthly_limit"] > 0:
                db.upsert_budget(str(row["category"]), float(row["monthly_limit"]))
        st.success(T["budget_saved"])
        st.rerun()


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


def _section_ledger(df: pd.DataFrame, T: dict[str, str], database_url: str) -> None:
    st.subheader(T["s5_heading"])
    st.caption(T["s5_caption"])
    st.caption(T["edit_cat_label"])
    st.caption(T["s5_duplicate_caption"])

    db = DatabaseClient(database_url)
    all_cats = db.get_categories()  # canonical list from categories table

    display = df[
        [
            "transaction_hash",
            "date",
            "owner_name",
            "account_name",
            "description",
            "adjusted_amount",
            "category",
            "is_recurring",
            "is_duplicate",
        ]
    ].copy()
    display.columns = [
        "hash",
        T["col_date"],
        T["col_owner"],
        T["col_account"],
        T["col_desc"],
        T["col_amount"],
        T["col_cat"],
        T["col_recurring"],
        T["col_duplicate"],
    ]

    editor_key = "ledger_editor"
    st.data_editor(
        display,
        key=editor_key,
        column_config={
            "hash": None,  # hidden
            T["col_cat"]: st.column_config.SelectboxColumn(
                T["col_cat"], options=all_cats, required=False
            ),
            T["col_recurring"]: st.column_config.CheckboxColumn(T["col_recurring"]),
            T["col_duplicate"]: st.column_config.CheckboxColumn(T["col_duplicate"]),
        },
        disabled=[
            T["col_date"],
            T["col_owner"],
            T["col_account"],
            T["col_desc"],
            T["col_amount"],
        ],
        use_container_width=True,
        hide_index=True,
    )

    # Only act on rows the user actually changed this render cycle
    editor_state = st.session_state.get(editor_key, {})
    for row_idx_str, col_changes in editor_state.get("edited_rows", {}).items():
        row_idx = int(row_idx_str)
        transaction_hash = display.iloc[row_idx]["hash"]
        if T["col_cat"] in col_changes:
            new_cat = col_changes[T["col_cat"]]
            if new_cat:
                db.update_transaction_category(str(transaction_hash), str(new_cat))
        if T["col_recurring"] in col_changes:
            new_recurring = col_changes[T["col_recurring"]]
            db.update_transaction_recurring(str(transaction_hash), bool(new_recurring))
        if T["col_duplicate"] in col_changes:
            new_duplicate = col_changes[T["col_duplicate"]]
            db.update_transaction_duplicate(str(transaction_hash), bool(new_duplicate))


def render_dashboard(
    tx_df: pd.DataFrame, acct_df: pd.DataFrame, database_url: str
) -> None:
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
        _section_net_worth(acct_df, T, lang, [], database_url)
        return

    tx = tx_df.copy()
    tx["date"] = pd.to_datetime(tx["date"])
    # Enrich once on the complete dataset so internal-transfer pair matching sees
    # both legs regardless of which owner/account filters are later applied.
    tx = _enrich_transactions(tx)

    filtered, all_time_filtered, selected_owners = _build_sidebar_filters(tx, T)

    if filtered.empty:
        st.info(T["no_transactions"])
        return

    # Rows the user has hand-flagged as double-posts are dropped from every analytical
    # frame (totals, charts, budgets, anomalies) but deliberately kept in the ledger's
    # frame: the ledger's checkbox is the only way to un-flag a row, so hiding flagged
    # rows there would make the flag irreversible. Filtering here — after the sidebar
    # has done its work — keeps both frames subject to the same period/owner/category
    # filters; only the is_duplicate rows differ.
    ledger_df = filtered
    not_duplicate = ~filtered["is_duplicate"].fillna(False).astype(bool)
    enriched = filtered[not_duplicate]
    enriched_all_time = all_time_filtered[
        ~all_time_filtered["is_duplicate"].fillna(False).astype(bool)
    ]

    tab_overview, tab_cashflow, tab_budget, tab_transactions = st.tabs(
        [T["tab_overview"], T["tab_cashflow"], T["tab_budget"], T["tab_transactions"]]
    )

    with tab_overview:
        _section_net_worth(acct_df, T, lang, selected_owners, database_url)
        st.divider()
        _section_overview(
            enriched, enriched_all_time, acct_df, T, lang, selected_owners
        )

    with tab_cashflow:
        _section_cash_flow(enriched, T)

    with tab_budget:
        _section_budget(enriched, T, database_url)

    with tab_transactions:
        _section_anomalies(enriched, T)
        st.divider()
        _section_ledger(ledger_df, T, database_url)
