"""Period/owner/category/... filtering for the dashboard read endpoints.

This is a **port**, not an extraction, of `app/dashboard.py::_build_sidebar_filters`
(lines 710-812). `app/dashboard.py` is frozen as of PLAN.md Phase 15, so the masking
logic is reimplemented here rather than lifted into a module both callers share. That
buys a real drift risk, which `tests/test_api_filters.py` exists to catch: every
non-obvious behaviour below is pinned by a test naming the Streamlit line it mirrors.

Three invariants carried over deliberately — each is load-bearing and each is easy to
"clean up" into a bug:

1. **Two frames, not one.** `apply_filters` returns `(filtered, all_time)`. `all_time`
   has every non-date filter applied but ignores the period, because trend charts and
   the emergency-fund metric must not collapse to a single point when the user picks a
   30-day window. Mirrors `_build_sidebar_filters`'s two return values.

2. **Filtering happens strictly downstream of enrichment.** `prepare_transactions` runs
   once over the complete dataset so internal-transfer pair matching sees both legs of a
   transfer even when one leg's account is filtered out. Never filter before enriching.

3. **The period selects whole MONTHS, not a date range.** `_preset_month_keys` resolves a
   preset to a date window, then keeps every month that window *touches* — so "last 30
   days" spanning a month boundary includes both months in full. This looks like a bug
   and is not: every aggregate downstream (budgets, month-over-month, the monthly trend
   lines) groups by month, and admitting half a month would render a partial month's
   spend as if it were a whole one. Month granularity in, month granularity out.

Anchoring also follows Streamlit: windows are measured back from the **latest transaction
date**, not from today. With a daily pipeline those coincide; when ingestion has stalled,
anchoring to `today` would silently return an empty dashboard instead of the most recent
data that exists.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

import pandas as pd
from fastapi import Depends, Query
from pydantic import BaseModel, Field

PeriodPreset = Literal[
    "last_30_days",
    "current_month",
    "last_3_months",
    "last_6_months",
    "ytd",
    "all_time",
    "custom",
]

# Streamlit defaults to last_30_days. The React dashboard defaults wider: with a 30-day
# window every "average monthly" figure averages exactly one month, which is the metric
# the user reported as misleading in the first place. See PLAN.md Phase 15, Fix 9.
DEFAULT_PERIOD: PeriodPreset = "last_3_months"


class DashboardFilters(BaseModel):
    """The 10 Streamlit sidebar filters, as query parameters."""

    period: PeriodPreset = DEFAULT_PERIOD
    months: list[str] | None = Field(
        default=None, description="Explicit `YYYY-MM` keys; only consulted when period='custom'."
    )
    owners: list[str] | None = None
    categories: list[str] | None = None
    accounts: list[str] | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    search: str | None = None
    outliers_only: bool = False
    duplicates_only: bool = False
    date_from: date | None = Field(
        default=None,
        description=(
            "Inclusive day-level lower bound, narrowing WITHIN whatever `period`/`months` already "
            "selects -- NOT a replacement for month-level filtering (the module's month-granularity "
            "invariant above is unchanged). Callers must ensure `period`/`months` already cover this "
            "range; `date_from`/`date_to` narrow further, they never widen. Added for a Cash Flow "
            "dashboard drill-down: jumping to a filtered Transactions view for exactly one week or one "
            "rolling-30-day window needs day precision the month-granularity filters can't express alone."
        ),
    )
    date_to: date | None = Field(
        default=None, description="Inclusive day-level upper bound. See `date_from`."
    )

    def is_default(self) -> bool:
        """True when nothing narrows the data — lets callers skip work and lets the UI
        decide whether to show a "clear filters" affordance."""
        return (
            self.period == DEFAULT_PERIOD
            and not self.months
            and not self.owners
            and not self.categories
            and not self.accounts
            and self.amount_min is None
            and self.amount_max is None
            and not self.search
            and not self.outliers_only
            and not self.duplicates_only
            and self.date_from is None
            and self.date_to is None
        )


def dashboard_filters(
    period: Annotated[PeriodPreset, Query()] = DEFAULT_PERIOD,
    months: Annotated[list[str] | None, Query()] = None,
    owners: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    accounts: Annotated[list[str] | None, Query()] = None,
    amount_min: Annotated[float | None, Query()] = None,
    amount_max: Annotated[float | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    outliers_only: Annotated[bool, Query()] = False,
    duplicates_only: Annotated[bool, Query()] = False,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> DashboardFilters:
    """FastAPI query-param dependency. Repeated params (`?owners=A&owners=B`) arrive as
    lists; omitting one entirely means "no constraint", which is not the same as an empty
    list, so the defaults are `None` rather than `[]`."""
    return DashboardFilters(
        period=period,
        months=months,
        owners=owners,
        categories=categories,
        accounts=accounts,
        amount_min=amount_min,
        amount_max=amount_max,
        search=search,
        outliers_only=outliers_only,
        duplicates_only=duplicates_only,
        date_from=date_from,
        date_to=date_to,
    )


FiltersDep = Annotated[DashboardFilters, Depends(dashboard_filters)]


def preset_month_keys(preset: PeriodPreset, df: pd.DataFrame) -> set[str]:
    """Month keys a quick-range preset touches, anchored to the latest transaction date.

    Port of `app/dashboard.py::_preset_month_keys` (lines 689-707). Reuses the `month`
    column `_enrich_transactions` already computes rather than recomputing Streamlit's
    private `_month_key` — same formula (`date.dt.to_period("M").astype(str)`).
    """
    if df.empty:
        return set()

    max_date = df["date"].max()
    if preset == "all_time":
        return set(df["month"].unique())

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

    window = df[(df["date"] >= start) & (df["date"] <= max_date)]
    return set(window["month"].unique())


def _non_date_mask(df: pd.DataFrame, filters: DashboardFilters) -> pd.Series:
    """Every filter except the period. Port of `app/dashboard.py` lines 782-805."""
    mask = pd.Series(True, index=df.index)

    if filters.owners:
        mask &= df["owner_name"].isin(filters.owners)
    if filters.categories:
        mask &= df["category"].isin(filters.categories)
    if filters.accounts:
        mask &= df["account_name"].isin(filters.accounts)

    if filters.amount_min is not None or filters.amount_max is not None:
        abs_amount = df["amount"].abs()
        lo = filters.amount_min
        hi = filters.amount_max
        # Tolerate an inverted range rather than silently returning zero rows —
        # `app/dashboard.py:768` makes the same allowance.
        if lo is not None and hi is not None and lo > hi:
            lo, hi = hi, lo
        if lo is not None:
            mask &= abs_amount >= lo
        if hi is not None:
            mask &= abs_amount <= hi

    if filters.search:
        # `regex=False` is a deliberate divergence from Streamlit, which leaves
        # `str.contains` in its default regex mode. Over HTTP that turns a description
        # search for "(" into a 500; a literal substring match is also what someone
        # typing into a search box actually means.
        mask &= df["description"].str.contains(filters.search, case=False, na=False, regex=False)

    if filters.outliers_only:
        mask &= df["is_outlier"].fillna(False).astype(bool)

    if filters.duplicates_only:
        # Grouped on `account_key`, NOT `account_name`: two distinct accounts can share a
        # display name, and collapsing them would invent duplicates that don't exist.
        # Mirrors `app/dashboard.py:788-792`.
        group_sizes = df.groupby(["account_key", "date", "description", "amount"], dropna=False)[
            "amount"
        ].transform("size")
        mask &= group_sizes > 1

    return mask


def apply_filters(df: pd.DataFrame, filters: DashboardFilters) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return `(filtered, all_time)`.

    `filtered` has every filter applied. `all_time` has everything except the period, and
    is what trend charts consume — see invariant 1 in the module docstring.

    `df` must already be enriched (`prepare_transactions`), never raw.
    """
    if df.empty:
        return df, df

    non_date = _non_date_mask(df, filters)

    if filters.period == "custom":
        selected_months = set(filters.months or [])
    else:
        selected_months = preset_month_keys(filters.period, df)

    date_mask = df["month"].isin(selected_months)
    # Day-level narrowing WITHIN the month selection above -- see `date_from`/`date_to`'s
    # docstrings. These never widen the window: a day outside the selected months stays
    # excluded even if it falls inside [date_from, date_to].
    if filters.date_from is not None:
        date_mask &= df["date"] >= pd.Timestamp(filters.date_from)
    if filters.date_to is not None:
        date_mask &= df["date"] <= pd.Timestamp(filters.date_to)
    return df[non_date & date_mask], df[non_date]


def build_filter_options(df: pd.DataFrame) -> dict:
    """Everything the filter UI needs to populate its controls, derived from the
    unfiltered frame so the option lists don't shrink as the user narrows the view."""
    if df.empty:
        return {
            "owners": [],
            "categories": [],
            "accounts": [],
            "months": [],
            "amount_min": 0.0,
            "amount_max": 0.0,
        }

    month_labels = (
        df[["month"]]
        .drop_duplicates()
        .assign(label=lambda x: pd.to_datetime(x["month"] + "-01").dt.strftime("%B %Y"))
        .sort_values("month")
    )
    abs_amounts = df["amount"].abs()
    return {
        "owners": sorted(df["owner_name"].dropna().unique().tolist()),
        "categories": sorted(df["category"].dropna().unique().tolist()),
        "accounts": sorted(df["account_name"].dropna().unique().tolist()),
        "months": [{"key": row["month"], "label": row["label"]} for _, row in month_labels.iterrows()],
        "amount_min": float(abs_amounts.min()),
        "amount_max": float(abs_amounts.max()),
    }
