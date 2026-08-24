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

**Unit contract (PLAN.md Phase 15, Fix 1).** Every ratio this module returns is a
*fraction*, not percentage points: a 60% savings rate is `0.6`. `credit_utilization.pct`
and `budget.pct` were already fractions while `savings_rate` was percentage points, and
the frontend applied one `formatPercent` to both — so one was always wrong. Do not
reintroduce a `* 100` here; formatting belongs to the UI.

**Divergence from Streamlit is intentional (PLAN.md Phase 15).** `app/dashboard.py` is
frozen, so it keeps the old percentage-point savings rate, the row-based rolling window,
and the 3-day stale-balance threshold. The five expected divergences are tabulated at the
end of Phase 15; anything else differing is a bug here.
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import Any

import pandas as pd

from app.dashboard import (
    _effective_credit_limit,
    _enrich_transactions,
    _label_subtype,
)

_IDENTITY_COLS = ["official_name", "account_subtype", "account_type", "mask"]

# Deliberately *not* imported from `app.dashboard._STALE_BALANCE_DAYS` (= 3), which is
# frozen. That constant conflated two different questions; Fix 5 splits them.
#   SYNC_STALE_DAYS  — `accounts.updated_at` is the last *balance refresh*. A gap here
#                      means the Plaid Item may be broken (see scripts/plaid_link.py
#                      repair), not that the account is unused.
#   DORMANT_DAYS     — no *transactions* in this long, i.e. an account you have probably
#                      stopped using. Informational, never a warning.
SYNC_STALE_DAYS = 7
DORMANT_DAYS = 90

# A month whose income is below this contributes no savings rate. Dividing a full month
# of expenses by a near-zero income produces a number with no meaning (the frozen
# Streamlit version clips income to $0.01 and reports -24,000,000%).
MIN_MONTHLY_INCOME_FOR_RATE = 100.0

# A calendar month needs at least this many days of observed coverage to count toward a
# "typical month" average. Excludes the in-progress current month and ragged window edges.
MIN_DAYS_FOR_COMPLETE_MONTH = 28

_ROLLING_SPEND_WINDOW_DAYS = 30


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


def complete_month_keys(df: pd.DataFrame) -> set[str]:
    """The `YYYY-MM` keys this frame covers in full.

    A "typical month" average must not mix whole months with fragments. The frame's
    first and last months are usually partial (the window cuts them mid-month), and the
    current calendar month is partial by definition — averaging a half-finished month in
    alongside complete ones drags the result toward whichever end has less data. That is
    Fix 3c: the reported "monthly expenses look off" symptom.

    Coverage is measured against the frame's own observed span, so a month is complete
    only when the data could have contained every one of its days.
    """
    if df.empty:
        return set()

    span_start = df["date"].min()
    span_end = df["date"].max()
    current_month = date.today().strftime("%Y-%m")

    complete: set[str] = set()
    for month_key in df["month"].unique():
        if month_key == current_month:
            continue
        period = pd.Period(month_key, freq="M")
        month_start = period.start_time
        month_end = period.end_time.normalize()
        observed_start = max(month_start, span_start)
        observed_end = min(month_end, span_end)
        covered_days = (observed_end - observed_start).days + 1
        if covered_days >= MIN_DAYS_FOR_COMPLETE_MONTH:
            complete.add(month_key)
    return complete


def _monthly_series(real: pd.DataFrame, tx_type: str, months: set[str]) -> pd.Series:
    """Per-month signed totals for one tx_type, restricted to `months`."""
    subset = real[(real["tx_type"] == tx_type) & (real["month"].isin(months))]
    if subset.empty:
        return pd.Series(dtype=float)
    return subset.groupby("month")["adjusted_amount"].sum()


def build_net_worth(
    acct_df: pd.DataFrame, tx_df: pd.DataFrame | None = None, lang: str = "en"
) -> dict[str, Any]:
    """Port of `_section_net_worth`'s data (not its widgets). No owner filtering —
    the Streamlit version's `selected_owners` came from the sidebar, which R2 has
    no equivalent of yet.

    `tx_df` is the **unfiltered** enriched transaction frame, used only to date each
    account's last activity for the dormant-account signal. It must stay unfiltered: a
    short period filter would otherwise make every account look dormant.
    """
    empty = {
        "net_worth": 0.0,
        "total_assets": 0.0,
        "total_liabilities": 0.0,
        "asset_mix": [],
        "owner_balances": [],
        "credit_utilization": [],
        "stale_accounts": [],
        "dormant_accounts": [],
        "forked_accounts": [],
    }
    if acct_df.empty:
        return empty

    assets_df = acct_df[acct_df["account_type"].isin(["depository", "investment"])].copy()
    credit_df = acct_df[acct_df["account_type"] == "credit"].copy()

    total_assets = float(assets_df["balance_current"].sum())
    total_liabilities = float(credit_df["balance_current"].sum())
    net_worth = total_assets - total_liabilities

    now = pd.Timestamp.now(tz="UTC")

    # --- Signal 1: sync health (last balance refresh), Fix 5 ------------------------
    updated = pd.to_datetime(acct_df["updated_at"], utc=True)
    stale_df = acct_df[updated < now - pd.Timedelta(days=SYNC_STALE_DAYS)]
    stale_accounts = [
        {
            "account_key": row["account_key"],
            "account_name": row["account_name"],
            "days_stale": int((now - pd.to_datetime(row["updated_at"], utc=True)).days),
        }
        for _, row in stale_df.iterrows()
    ]

    # --- Signal 2: dormancy (last transaction), Fix 5 -------------------------------
    dormant_accounts: list[dict[str, Any]] = []
    if tx_df is not None and not tx_df.empty:
        last_activity = tx_df.groupby("account_key")["date"].max()
        today = pd.Timestamp(date.today())
        for _, row in acct_df.iterrows():
            balance = float(row["balance_current"])
            if balance == 0.0:
                # A dormant account with nothing in it needs no attention.
                continue
            last_seen = last_activity.get(row["account_key"])
            if pd.isna(last_seen):
                continue
            days_inactive = int((today - pd.Timestamp(last_seen).normalize()).days)
            if days_inactive >= DORMANT_DAYS:
                dormant_accounts.append(
                    {
                        "account_key": row["account_key"],
                        "account_name": row["account_name"],
                        "owner_name": _clean(row["owner_name"]),
                        "days_inactive": days_inactive,
                        "balance": balance,
                    }
                )
        dormant_accounts.sort(key=lambda r: r["days_inactive"], reverse=True)

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

    # --- Owner balances: one row per OWNER, not per account (Fix 4) -----------------
    # Emitting a row per account left Recharts drawing N bars whose x-axis label took
    # only two distinct values, so "Alexie"/"Jacob" repeated at irregular intervals.
    # Streamlit's equivalent is a stacked bar (x=owner, colour=account_type); this is
    # that shape. Per-account detail moves into `accounts` for the tooltip.
    owner_rows: dict[str, dict[str, Any]] = {}
    for _, row in acct_df.iterrows():
        owner = _clean(row["owner_name"]) or "Unknown"
        account_type = row["account_type"]
        raw = float(row["balance_current"])
        # Credit balances are money owed: negate so liabilities sit below the zero line.
        signed = -raw if account_type == "credit" else raw
        bucket = account_type if account_type in ("depository", "investment", "credit") else "other"
        entry = owner_rows.setdefault(
            owner,
            {
                "owner": owner,
                "depository": 0.0,
                "investment": 0.0,
                "credit": 0.0,
                "other": 0.0,
                "net": 0.0,
                "accounts": [],
            },
        )
        entry[bucket] += signed
        entry["net"] += signed
        entry["accounts"].append({"account_name": row["account_name"], "type": account_type, "value": signed})
    owner_balances = sorted(owner_rows.values(), key=lambda r: r["net"], reverse=True)

    credit_utilization = []
    for _, row in credit_df.iterrows():
        current = float(row["balance_current"])
        limit, is_manual = _effective_credit_limit(row["balance_limit"], row["manual_credit_limit"])
        credit_utilization.append(
            {
                "account_key": row["account_key"],
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
        "dormant_accounts": dormant_accounts,
        "forked_accounts": forked_accounts,
    }


def build_overview(
    df: pd.DataFrame, acct_df: pd.DataFrame, all_time_df: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Port of `_section_overview`'s data. `df` must already be enriched
    (`prepare_transactions`) and duplicate-excluded.

    `all_time_df` is the same frame with every filter EXCEPT the period applied — see
    `api/filters.py`, invariant 1. Headline figures and the monthly/weekly averages read
    the period-filtered `df`; trends, the 12-month category breakdowns, and the emergency
    fund read `all_time_df`, so picking a 30-day window doesn't collapse a year-long trend
    line to a single point. Defaults to `df` for callers with no period filter.
    """
    if all_time_df is None:
        all_time_df = df
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
        "avg_monthly_net": 0.0,
        "complete_months": 0,
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
    # Fraction, not percentage points — see the unit contract in the module docstring.
    savings_rate = (net_flow / income) if income > 0 else 0.0
    flagged_count = int(df["is_outlier"].sum())

    # Weekly averages keep the zero-filled unstack: an inactive week is a real zero.
    weekly_totals = real.groupby(["week", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0)
    avg_weekly_expense = float(weekly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0)
    avg_weekly_income = float(weekly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0)

    # Monthly averages count only months observed in full (Fix 3c).
    months = complete_month_keys(df)
    monthly_expense_series = _monthly_series(real, "expense", months)
    monthly_income_series = _monthly_series(real, "income", months)
    avg_monthly_expense = float(monthly_expense_series.abs().mean() or 0.0)
    avg_monthly_income = float(monthly_income_series.mean() or 0.0)
    # The tile beside these two used the ALL-TIME net_flow, so it was larger than its
    # neighbours by however many months of history existed (Fix 3a).
    avg_monthly_net = avg_monthly_income - avg_monthly_expense

    max_date = all_time_df["date"].max()
    bounded_all_time = all_time_df[all_time_df["date"] >= max_date - pd.DateOffset(months=12)]

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

    # An account frame can legitimately be empty (dashboard-only deploys, or a fresh
    # database), in which case there is no liquid balance to divide by.
    liquid_assets = 0.0
    if not acct_df.empty and "account_type" in acct_df.columns:
        liquid_assets = float(acct_df[acct_df["account_type"].isin(["depository"])]["balance_current"].sum())
    # Coverage is a property of your life, not of the window you happen to be looking at,
    # so this averages over all history rather than the selected period.
    emergency_fund_months = None
    all_time_real = all_time_df[all_time_df["tx_type"] != "transfer"]
    all_time_expenses = _monthly_series(all_time_real, "expense", complete_month_keys(all_time_df))
    if not all_time_expenses.empty:
        avg_monthly_expenses = float(all_time_expenses.abs().mean())
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

    # --- Savings-rate trend (Fix 2) -------------------------------------------------
    # The frozen Streamlit version divides by `income.clip(lower=0.01)`, so a $0-income
    # month reports millions of percent. A month with no meaningful income has no
    # meaningful savings rate; say so with None and let the chart draw a gap.
    savings_rate_trend = []
    non_transfer = all_time_df[all_time_df["tx_type"] != "transfer"]
    if not non_transfer.empty:
        by_month = non_transfer.groupby(["month", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0.0)
        for month_key in sorted(by_month.index):
            month_income = float(by_month.get("income", pd.Series(dtype=float)).get(month_key, 0.0))
            month_expenses = abs(float(by_month.get("expense", pd.Series(dtype=float)).get(month_key, 0.0)))
            rate = (
                (month_income - month_expenses) / month_income
                if month_income >= MIN_MONTHLY_INCOME_FOR_RATE
                else None
            )
            savings_rate_trend.append(
                {
                    "month": month_key,
                    "savings_rate": rate,
                    "income": month_income,
                    "expenses": month_expenses,
                }
            )

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
        "avg_monthly_net": avg_monthly_net,
        "complete_months": len(months),
        "top_categories": top_categories,
        "month_over_month": month_over_month,
        "emergency_fund_months": emergency_fund_months,
        "income_breakdown": income_breakdown,
        "savings_rate_trend": savings_rate_trend,
    }


def _wide_flow_series(df: pd.DataFrame, key: str) -> list[dict[str, Any]]:
    """Income/expense/net totals per period, in **wide** rows.

    Long rows (`{period, tx_type, amount}`) forced the frontend to pivot by matching on
    the `tx_type` string, and it matched on `"INCOME"`/`"EXPENSE"` while this module
    emits lowercase — so both `<Bar>`s bound to `undefined` and the chart rendered axes
    with no bars (Fix 6). Emitting wide rows removes the pivot, and with it the bug class.
    """
    non_transfer = df[df["tx_type"] != "transfer"]
    if non_transfer.empty:
        return []
    grouped = non_transfer.groupby([key, "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0.0)
    income_col = grouped.get("income", pd.Series(0.0, index=grouped.index))
    expense_col = grouped.get("expense", pd.Series(0.0, index=grouped.index)).abs()
    return [
        {
            key: period,
            "income": float(income_col.get(period, 0.0)),
            "expenses": float(expense_col.get(period, 0.0)),
            "net": float(income_col.get(period, 0.0) - expense_col.get(period, 0.0)),
        }
        for period in sorted(grouped.index)
    ]


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
    # Positive magnitude, matching build_overview. This builder used to return a signed
    # (negative) figure while build_overview returned a positive one, so the Cash Flow
    # tab printed a negative number in red under "Total Expenses" (Fix 8).
    expenses = float(abs(real[real["tx_type"] == "expense"]["adjusted_amount"].sum()))
    net_flow = income - expenses
    transfer_count = int((df["tx_type"] == "transfer").sum())
    flagged_count = int(df["is_outlier"].sum())
    savings_rate = (net_flow / income) if income > 0 else 0.0

    month_over_month = _wide_flow_series(df, "month")
    weekly_trend = _wide_flow_series(df, "week")

    # --- Rolling 30-day spend (Fix 7) ----------------------------------------------
    # `.rolling(30)` over a date-GROUPED frame counts 30 rows, not 30 days: with sparse
    # days a nominal "30-day" window silently spans months. Reindex to a continuous
    # daily index and use a time-based window so the label is true.
    rolling_30d_spend: list[dict[str, Any]] = []
    expense_rows = real[real["tx_type"] == "expense"]
    if not expense_rows.empty:
        daily = expense_rows.groupby("date")["adjusted_amount"].sum().abs().sort_index()
        full_index = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
        daily = daily.reindex(full_index, fill_value=0.0)
        rolling = daily.rolling(f"{_ROLLING_SPEND_WINDOW_DAYS}D").sum()
        # Drop the ramp out of a partial window, which reads as a spending trend that
        # isn't real. Keep everything when there is less than one full window of data —
        # an empty chart is worse than a short one.
        span_days = (daily.index.max() - daily.index.min()).days + 1
        if span_days >= _ROLLING_SPEND_WINDOW_DAYS:
            cutoff = daily.index.min() + pd.Timedelta(days=_ROLLING_SPEND_WINDOW_DAYS - 1)
            rolling = rolling[rolling.index >= cutoff]
        rolling_30d_spend = [
            {
                "date": stamp.date().isoformat(),
                "amount": float(total),
                "daily_avg": float(total) / _ROLLING_SPEND_WINDOW_DAYS,
            }
            for stamp, total in rolling.items()
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
