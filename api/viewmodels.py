"""Pure JSON-view-model builders for the React dashboard's read endpoints.

Ports the section renderers in `app/dashboard.py` (`_section_net_worth`,
`_section_overview`, `_section_cash_flow`, `_section_budget`, `_section_anomalies`,
`_section_ledger`) from Streamlit widget calls to plain dict/list return values.
Reuses (does not reimplement) the pure functions those renderers call — see the
`from app.dashboard import ...` below — so the underlying business logic (net worth,
cash-flow, tx-type classification, credit-limit resolution) stays covered by the
tests already in `tests/test_dashboard_classify.py` / `tests/test_dashboard_helpers.py`.

Scope decision (judgment call — the plan left exact view-model shapes open): unlike
the Streamlit sidebar, these builders take no period/owner/category filter params in
R2 — they compute over the full history (minus rows flagged `is_duplicate`, mirroring
the Streamlit "enriched" frame). The ledger view model is the one exception: it keeps
duplicate-flagged rows, same as `_section_ledger`, because the ledger's checkbox is
the only way to un-flag a row. Adding query-param filtering later is additive to this
shape, not breaking.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

import pandas as pd

from app.dashboard import (
    _STALE_BALANCE_DAYS,
    _effective_credit_limit,
    _enrich_transactions,
    _label_subtype,
)

_IDENTITY_COLS = ["official_name", "account_subtype", "account_type", "mask"]


def exclude_duplicate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows the user has hand-flagged `is_duplicate`, same as the Streamlit
    "enriched" frame used by every section except the ledger."""
    if df.empty:
        return df
    return df[~df["is_duplicate"].fillna(False).astype(bool)]


def prepare_transactions(tx_df: pd.DataFrame) -> pd.DataFrame:
    """Mirror `render_dashboard`'s prep: parse dates, enrich once on the full frame
    so internal-transfer pair matching sees both legs of a transfer regardless of
    which rows get filtered out downstream."""
    if tx_df.empty:
        return tx_df
    tx = tx_df.copy()
    tx["date"] = pd.to_datetime(tx["date"])
    return _enrich_transactions(tx)


def _clean(value: Any) -> Any:
    """None for NaN/NaT, else the raw value — pandas leaves NULLs as NaN, which
    isn't valid JSON and doesn't satisfy an `Optional[str]` Pydantic field."""
    return None if pd.isna(value) else value


def build_net_worth(acct_df: pd.DataFrame, lang: str = "en") -> dict[str, Any]:
    """Port of `_section_net_worth`'s data (not its widgets). No owner filtering —
    the Streamlit version's `selected_owners` came from the sidebar, which R2 has
    no equivalent of yet."""
    if acct_df.empty:
        return {
            "net_worth": 0.0,
            "total_assets": 0.0,
            "total_liabilities": 0.0,
            "asset_mix": [],
            "owner_balances": [],
            "credit_utilization": [],
            "stale_accounts": [],
            "forked_accounts": [],
        }

    assets_df = acct_df[acct_df["account_type"].isin(["depository", "investment"])].copy()
    credit_df = acct_df[acct_df["account_type"] == "credit"].copy()

    total_assets = float(assets_df["balance_current"].sum())
    total_liabilities = float(credit_df["balance_current"].sum())
    net_worth = total_assets - total_liabilities

    stale_cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=_STALE_BALANCE_DAYS)
    stale_df = acct_df[pd.to_datetime(acct_df["updated_at"], utc=True) < stale_cutoff]
    stale_accounts = [
        {
            "account_name": row["account_name"],
            "days_stale": int(
                (pd.Timestamp.now(tz="UTC") - pd.to_datetime(row["updated_at"], utc=True)).days
            ),
        }
        for _, row in stale_df.iterrows()
    ]

    identifiable = acct_df.dropna(subset=_IDENTITY_COLS)
    forked_accounts: list[str] = []
    if not identifiable.empty:
        fork_sizes = identifiable.groupby(_IDENTITY_COLS)["account_key"].transform("size")
        forked_df = identifiable[fork_sizes > 1]
        forked_accounts = sorted(forked_df["account_name"].unique().tolist())

    asset_mix: list[dict[str, Any]] = []
    if not assets_df.empty:
        assets_df["subtype_label"] = assets_df["account_subtype"].apply(lambda s: _label_subtype(s, lang))
        asset_mix = [
            {"subtype_label": subtype_label, "balance": float(balance)}
            for subtype_label, balance in assets_df.groupby("subtype_label")["balance_current"].sum().items()
        ]

    owner_balances = []
    for _, row in acct_df.iterrows():
        val = row["balance_current"] if row["account_type"] != "credit" else -row["balance_current"]
        owner_balances.append(
            {
                "owner": _clean(row["owner_name"]) or "Unknown",
                "value": float(val),
                "type": row["account_type"],
            }
        )

    credit_utilization = []
    for _, row in credit_df.iterrows():
        current = float(row["balance_current"])
        limit, is_manual = _effective_credit_limit(row["balance_limit"], row["manual_credit_limit"])
        credit_utilization.append(
            {
                "account_name": row["account_name"],
                "owner_name": _clean(row["owner_name"]),
                "current": current,
                "limit": float(limit) if limit is not None else None,
                "pct": (current / limit) if limit else None,
                "is_manual": is_manual,
            }
        )

    return {
        "net_worth": net_worth,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "asset_mix": asset_mix,
        "owner_balances": owner_balances,
        "credit_utilization": credit_utilization,
        "stale_accounts": stale_accounts,
        "forked_accounts": forked_accounts,
    }


def build_overview(df: pd.DataFrame, acct_df: pd.DataFrame) -> dict[str, Any]:
    """Port of `_section_overview`'s data. `df` must already be enriched
    (`prepare_transactions`) and duplicate-excluded."""
    empty_result = {
        "income": 0.0,
        "expenses": 0.0,
        "net_flow": 0.0,
        "savings_rate": 0.0,
        "flagged_count": 0,
        "avg_weekly_expense": 0.0,
        "avg_monthly_expense": 0.0,
        "avg_weekly_income": 0.0,
        "avg_monthly_income": 0.0,
        "top_categories": [],
        "month_over_month": [],
        "emergency_fund_months": None,
        "income_breakdown": [],
        "savings_rate_trend": [],
    }
    if df.empty:
        return empty_result

    real = df[df["tx_type"] != "transfer"]
    income = float(real[real["tx_type"] == "income"]["adjusted_amount"].sum())
    expenses = float(abs(real[real["tx_type"] == "expense"]["adjusted_amount"].sum()))
    net_flow = income - expenses
    savings_rate = (net_flow / income * 100) if income > 0 else 0.0
    flagged_count = int(df["is_outlier"].sum())

    weekly_totals = real.groupby(["week", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0)
    monthly_totals = real.groupby(["month", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0)

    avg_weekly_expense = float(weekly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0)
    avg_monthly_expense = float(monthly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0)
    avg_weekly_income = float(weekly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0)
    avg_monthly_income = float(monthly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0)

    max_date = df["date"].max()
    bounded_all_time = df[df["date"] >= max_date - pd.DateOffset(months=12)]

    top_cats_df = (
        bounded_all_time[bounded_all_time["tx_type"] == "expense"]
        .groupby("category", as_index=False)["adjusted_amount"]
        .sum()
        .assign(abs_amount=lambda x: x["adjusted_amount"].abs())
        .nlargest(10, "abs_amount")
        .sort_values("abs_amount", ascending=False)
    )
    top_categories = [
        {"category": row["category"], "amount": float(row["abs_amount"])} for _, row in top_cats_df.iterrows()
    ]

    month_over_month = []
    months_sorted = sorted(bounded_all_time["month"].unique())
    if len(months_sorted) >= 2:
        this_m, last_m = months_sorted[-1], months_sorted[-2]
        mom = bounded_all_time[
            bounded_all_time["month"].isin([this_m, last_m]) & (bounded_all_time["tx_type"] == "expense")
        ]
        mom_grp = mom.groupby(["category", "month"], as_index=False)["adjusted_amount"].sum()
        mom_grp["abs_amount"] = mom_grp["adjusted_amount"].abs()
        mom_grp["period"] = mom_grp["month"].map({this_m: "this_month", last_m: "last_month"})
        month_over_month = [
            {"category": row["category"], "period": row["period"], "amount": float(row["abs_amount"])}
            for _, row in mom_grp.iterrows()
        ]

    liquid_assets = float(acct_df[acct_df["account_type"].isin(["depository"])]["balance_current"].sum())
    monthly_expenses_series = df[df["tx_type"] == "expense"].groupby("month")["adjusted_amount"].sum().abs()
    emergency_fund_months = None
    if not monthly_expenses_series.empty:
        avg_monthly_expenses = monthly_expenses_series.mean()
        if avg_monthly_expenses > 0:
            emergency_fund_months = float(liquid_assets / avg_monthly_expenses)

    income_src_df = (
        df[df["tx_type"] == "income"]
        .groupby("description", as_index=False)["adjusted_amount"]
        .sum()
        .nlargest(8, "adjusted_amount")
    )
    income_breakdown = [
        {"description": row["description"], "amount": float(row["adjusted_amount"])}
        for _, row in income_src_df.iterrows()
    ]

    savings_rate_trend = []
    monthly = (
        df[df["tx_type"] != "transfer"]
        .groupby("month")
        .apply(
            lambda g: pd.Series(
                {
                    "income": g.loc[g["tx_type"] == "income", "adjusted_amount"].sum(),
                    "expenses": abs(g.loc[g["tx_type"] == "expense", "adjusted_amount"].sum()),
                }
            )
        )
        .reset_index()
    )
    if not monthly.empty:
        monthly["savings_rate"] = (
            (monthly["income"] - monthly["expenses"]) / monthly["income"].clip(lower=0.01) * 100
        )
        savings_rate_trend = [
            {"month": row["month"], "savings_rate": float(row["savings_rate"])}
            for _, row in monthly.iterrows()
        ]

    return {
        "income": income,
        "expenses": expenses,
        "net_flow": net_flow,
        "savings_rate": savings_rate,
        "flagged_count": flagged_count,
        "avg_weekly_expense": avg_weekly_expense,
        "avg_monthly_expense": avg_monthly_expense,
        "avg_weekly_income": avg_weekly_income,
        "avg_monthly_income": avg_monthly_income,
        "top_categories": top_categories,
        "month_over_month": month_over_month,
        "emergency_fund_months": emergency_fund_months,
        "income_breakdown": income_breakdown,
        "savings_rate_trend": savings_rate_trend,
    }


def build_cash_flow(df: pd.DataFrame) -> dict[str, Any]:
    """Port of `_section_cash_flow`'s data. `df` must already be enriched and
    duplicate-excluded."""
    empty_result = {
        "income": 0.0,
        "expenses": 0.0,
        "net_flow": 0.0,
        "transfer_count": 0,
        "flagged_count": 0,
        "savings_rate": 0.0,
        "month_over_month": [],
        "weekly_trend": [],
        "rolling_30d_spend": [],
        "monthly_net_by_owner": [],
        "category_distribution": [],
    }
    if df.empty:
        return empty_result

    real = df[df["tx_type"] != "transfer"]
    income = float(real[real["tx_type"] == "income"]["adjusted_amount"].sum())
    expenses = float(real[real["tx_type"] == "expense"]["adjusted_amount"].sum())
    net_flow = income + expenses
    transfer_count = int((df["tx_type"] == "transfer").sum())
    flagged_count = int(df["is_outlier"].sum())
    savings_rate = (net_flow / income * 100) if income > 0 else 0.0

    mom_summary = (
        df[df["tx_type"] != "transfer"].groupby(["month", "tx_type"], as_index=False)["adjusted_amount"].sum()
    )
    mom_summary.loc[mom_summary["tx_type"] == "expense", "adjusted_amount"] = mom_summary.loc[
        mom_summary["tx_type"] == "expense", "adjusted_amount"
    ].abs()
    month_over_month = [
        {"month": row["month"], "tx_type": row["tx_type"], "amount": float(row["adjusted_amount"])}
        for _, row in mom_summary.iterrows()
    ]

    week_summary = (
        df[df["tx_type"] != "transfer"].groupby(["week", "tx_type"], as_index=False)["adjusted_amount"].sum()
    )
    week_summary.loc[week_summary["tx_type"] == "expense", "adjusted_amount"] = week_summary.loc[
        week_summary["tx_type"] == "expense", "adjusted_amount"
    ].abs()
    weekly_trend = [
        {"week": row["week"], "tx_type": row["tx_type"], "amount": float(row["adjusted_amount"])}
        for _, row in week_summary.iterrows()
    ]

    spend = (
        real[real["tx_type"] == "expense"]
        .groupby("date", as_index=False)["adjusted_amount"]
        .sum()
        .sort_values("date")
    )
    spend["abs_spend"] = spend["adjusted_amount"].abs()
    spend["rolling_30d"] = spend["abs_spend"].rolling(30, min_periods=1).sum()
    rolling_30d_spend = [
        {"date": row["date"].date().isoformat(), "amount": float(row["rolling_30d"])}
        for _, row in spend.iterrows()
    ]

    split = real.groupby(["month", "owner_name"], as_index=False)["adjusted_amount"].sum()
    monthly_net_by_owner = [
        {
            "month": row["month"],
            "owner": _clean(row["owner_name"]) or "Unknown",
            "amount": float(row["adjusted_amount"]),
        }
        for _, row in split.iterrows()
    ]

    exp_only = real[real["tx_type"] == "expense"].copy()
    exp_only["abs_amount"] = exp_only["adjusted_amount"].abs()
    dist = exp_only.groupby(["month", "category"], as_index=False)["abs_amount"].sum()
    category_distribution = [
        {"month": row["month"], "category": row["category"], "amount": float(row["abs_amount"])}
        for _, row in dist.iterrows()
    ]

    return {
        "income": income,
        "expenses": expenses,
        "net_flow": net_flow,
        "transfer_count": transfer_count,
        "flagged_count": flagged_count,
        "savings_rate": savings_rate,
        "month_over_month": month_over_month,
        "weekly_trend": weekly_trend,
        "rolling_30d_spend": rolling_30d_spend,
        "monthly_net_by_owner": monthly_net_by_owner,
        "category_distribution": category_distribution,
    }


def build_budget(df: pd.DataFrame, budget_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Port of `_section_budget`'s data. `df` must already be enriched and
    duplicate-excluded. `budget_rows` is `DatabaseClient.get_budgets()`'s return value."""
    budget_map = {r["category"]: r["monthly_limit"] for r in budget_rows}

    current_month_str = None if df.empty else df["month"].max()
    today = date.today()
    is_current_month = current_month_str == today.strftime("%Y-%m")

    if df.empty:
        period_expenses: dict[str, float] = {}
    else:
        period_expenses = (
            df[(df["month"] == current_month_str) & (df["tx_type"] == "expense")]
            .groupby("category")["adjusted_amount"]
            .sum()
            .abs()
            .to_dict()
        )

    projection_factor = None
    if is_current_month:
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_elapsed = max(today.day, 1)
        projection_factor = days_in_month / days_elapsed

    all_categories = sorted(set(period_expenses.keys()) | set(budget_map.keys()))

    items = []
    for cat in all_categories:
        spent = float(period_expenses.get(cat, 0.0))
        limit = budget_map.get(cat)
        projected_eom = spent * projection_factor if projection_factor is not None else None
        pct = min(spent / limit, 1.0) if limit else None
        items.append(
            {
                "category": cat,
                "spent": spent,
                "limit": float(limit) if limit is not None else None,
                "pct": pct,
                "is_over_budget": bool(limit and spent > limit),
                "projected_eom": projected_eom,
                "is_current_month": is_current_month,
            }
        )

    return {"month": current_month_str, "items": items}


def build_anomalies(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Port of `_section_anomalies`'s data. `df` must already be enriched and
    duplicate-excluded."""
    if df.empty:
        return []
    outliers = df[df["is_outlier"]].copy()
    if outliers.empty:
        return []
    outliers = outliers.sort_values("date", ascending=False)
    return [
        {
            "date": row["date"].date().isoformat(),
            "owner_name": _clean(row["owner_name"]),
            "account_name": row["account_name"],
            "description": row["description"],
            "amount": float(row["adjusted_amount"]),
            "category": _clean(row["category"]),
            "outlier_score": float(row["outlier_score"]),
        }
        for _, row in outliers.iterrows()
    ]


def build_ledger(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Port of `_section_ledger`'s data. `df` must already be enriched. Unlike every
    other builder, `is_duplicate` rows are kept — the ledger's checkbox is the only
    way to un-flag one."""
    if df.empty:
        return []
    ordered = df.sort_values("date", ascending=False)
    return [
        {
            "hash": row["transaction_hash"],
            "date": row["date"].date().isoformat(),
            "owner_name": _clean(row["owner_name"]),
            "account_name": row["account_name"],
            "description": row["description"],
            "amount": float(row["adjusted_amount"]),
            "category": _clean(row["category"]),
            "is_recurring": bool(row["is_recurring"]) if pd.notna(row["is_recurring"]) else False,
            "is_duplicate": bool(row["is_duplicate"]) if pd.notna(row["is_duplicate"]) else False,
        }
        for _, row in ordered.iterrows()
    ]
