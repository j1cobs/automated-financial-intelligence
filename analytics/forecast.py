"""Forward cash-flow projection (Phase 32).

This is what turns the Budget tab from a scorecard into a planning tool: not
"did I overspend last month" but "what will I have on hand in March".

Two series come back on every row:

  ``projected_balance`` — **behaviour.** Known recurring streams land on their
  predicted dates; everything else is a trailing median per category. This is
  the honest projection: what will probably happen.

  ``budget_balance`` — **intent.** The same, but every category held to its cap.
  Forecasting from caps alone was rejected: it projects a world in which you hit
  every target, which is an aspiration, not a forecast. Carrying both makes the
  *gap* visible, and that gap is the value of sticking to budget.

A cap is a ceiling, not a target: a category already spending under its cap is
not inflated up to it.

Three guards matter:

  - **Thin history refuses.** `days_back` defaults to 90, so a median over two
    months is the normal early case. Below `MIN_MONTHS_FOR_FORECAST` this
    returns no rows and says why, rather than dressing a guess as a projection.
  - **The current month is excluded from the baseline.** A partial month has
    partial spend; letting it in would drag the median down and flatter the
    forecast.
  - **Starting balance is spendable cash only** — see `starting_balance`.
"""

from __future__ import annotations

import statistics
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

__all__ = [
    "DEFAULT_HORIZON_MONTHS",
    "MAX_HORIZON_MONTHS",
    "MIN_MONTHS_FOR_FORECAST",
    "project",
    "starting_balance",
]

DEFAULT_HORIZON_MONTHS = 6

#: Hard ceiling. A goal dated decades out must not turn a chart into hundreds
#: of rows -- the projection is worthless that far ahead anyway.
MAX_HORIZON_MONTHS = 36

#: Complete months of history required before projecting at all.
MIN_MONTHS_FOR_FORECAST = 3

#: Nominal cadence lengths, for placing a recurring stream in future months.
_CADENCE_MONTHS: dict[str, float] = {
    "WEEKLY": 7 / 30.44,
    "BIWEEKLY": 14 / 30.44,
    "MONTHLY": 1.0,
    "ANNUALLY": 12.0,
}


def starting_balance(accounts: pd.DataFrame) -> float:
    """Spendable cash: `account_type == 'depository'` only.

    Credit balances are negative and their repayment already shows up as a
    recurring outflow, so including them would double-count. Investment
    balances move with the market, which transaction history cannot forecast —
    projecting them would present noise as a prediction.

    This is the same filter already used at `api/viewmodels.py:393`/`:844` and
    `app/dashboard.py:919`, not a new convention.
    """
    if accounts is None or accounts.empty:
        return 0.0
    if "account_type" not in accounts.columns or "balance_current" not in accounts.columns:
        return 0.0
    depository = accounts[accounts["account_type"] == "depository"]
    if depository.empty:
        return 0.0
    return float(depository["balance_current"].fillna(0.0).sum())


def _add_months(period: str, count: int) -> str:
    year, month = (int(part) for part in period.split("-"))
    total = (year * 12 + (month - 1)) + count
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _months_between(start: str, end: str) -> int:
    start_year, start_month = (int(part) for part in start.split("-"))
    end_year, end_month = (int(part) for part in end.split("-"))
    return (end_year * 12 + end_month) - (start_year * 12 + start_month)


def _monthly_stream_cost(streams: list[dict[str, Any]], period: str) -> float:
    """Outflow from recurring streams falling in `period`.

    A stream is placed by stepping its cadence forward from its predicted next
    date, so an annual charge lands in one month rather than being smeared
    across twelve.
    """
    total = 0.0
    for stream in streams:
        if not stream.get("is_active", True) or stream.get("direction") != "outflow":
            continue
        next_date = stream.get("predicted_next_date")
        if next_date is None:
            continue
        if isinstance(next_date, str):
            next_date = date.fromisoformat(next_date)

        cadence_months = _CADENCE_MONTHS.get(stream.get("cadence") or "", 0.0)
        if cadence_months <= 0:
            continue

        start_period = f"{next_date.year:04d}-{next_date.month:02d}"
        offset = _months_between(start_period, period)
        if offset < 0:
            continue

        amount = abs(float(stream.get("last_amount") or 0.0))
        if cadence_months <= 1.0:
            # Sub-monthly cadences recur within every month.
            total += amount * (1.0 / cadence_months)
        elif offset % int(round(cadence_months)) == 0:
            total += amount
    return total


def project(
    frame: pd.DataFrame,
    streams: list[dict[str, Any]],
    caps: dict[str, Decimal],
    starting: float,
    horizon_months: int = DEFAULT_HORIZON_MONTHS,
    today: date | None = None,
    furthest_goal_date: date | None = None,
    max_horizon_months: int = MAX_HORIZON_MONTHS,
) -> dict[str, Any]:
    """Project `horizon_months` forward from `starting`.

    `frame` must be enriched (`month`, `tx_type`, `category`, `adjusted_amount`)
    and duplicate-excluded. `caps` is `resolve_caps`'s output for the current
    month. The horizon extends to cover `furthest_goal_date` when that is
    further out, so a goal is visible on the chart it is planned with.
    """
    reference = today or date.today()
    current_period = reference.strftime("%Y-%m")

    empty = {
        "rows": [],
        "has_enough_history": False,
        "has_recurring_data": bool(streams),
        "months_of_history": 0,
        "starting_balance": float(starting),
    }
    if frame is None or frame.empty:
        return empty
    if not {"month", "tx_type", "category", "adjusted_amount"}.issubset(frame.columns):
        return empty

    # The in-progress month has partial spend; including it would drag every
    # median down and make the forecast look better than it is.
    complete = frame[frame["month"] < current_period]
    months = sorted(complete["month"].unique().tolist())
    if len(months) < MIN_MONTHS_FOR_FORECAST:
        return {**empty, "months_of_history": len(months)}

    expenses = complete[complete["tx_type"] == "expense"]
    income = complete[complete["tx_type"] == "income"]

    # Median, not mean: one unusual month should not set the baseline.
    #
    # Reindexed over EVERY month, matching the per-category treatment below. A
    # median over only the months that happen to contain income rows reads
    # irregular income (freelance, bonuses) as though it arrived every month,
    # and the projected balance then climbs faster than reality forever.
    if income.empty:
        monthly_income = 0.0
    else:
        income_by_month = income.groupby("month")["adjusted_amount"].sum().abs()
        monthly_income = statistics.median(
            [float(income_by_month.get(month, 0.0)) for month in months]
        )

    per_category: dict[str, float] = {}
    if not expenses.empty:
        for category, group in expenses.groupby("category"):
            by_month = group.groupby("month")["adjusted_amount"].sum().abs()
            # Reindex over every month so a category absent in some months is
            # averaged as zero there rather than as though it never lapsed.
            values = [float(by_month.get(month, 0.0)) for month in months]
            per_category[str(category)] = statistics.median(values)

    horizon = horizon_months
    if furthest_goal_date is not None:
        goal_period = f"{furthest_goal_date.year:04d}-{furthest_goal_date.month:02d}"
        horizon = max(horizon, _months_between(current_period, goal_period))
    # Clamped: extending to reach a goal is useful, but a goal dated 2060 must
    # not build 400 rows to serialize and plot.
    horizon = max(1, min(horizon, max_horizon_months))

    rows: list[dict[str, Any]] = []
    balance = float(starting)
    budget_balance = float(starting)

    for step in range(1, horizon + 1):
        period = _add_months(current_period, step)

        stream_cost = _monthly_stream_cost(streams, period)
        # Streams are a subset of category spend, so adding both would
        # double-count. The medians already contain them; streams only sharpen
        # *when* the money leaves, so take the larger of the two per month.
        behaviour_expense = max(sum(per_category.values()), stream_cost)

        capped_expense = 0.0
        for category, median in per_category.items():
            cap = caps.get(category)
            # A cap is a ceiling, not a target: never spend a category up to it.
            capped_expense += min(median, float(cap)) if cap is not None else median
        capped_expense = max(capped_expense, stream_cost)

        balance += monthly_income - behaviour_expense
        budget_balance += monthly_income - capped_expense

        rows.append(
            {
                "month": period,
                "projected_balance": balance,
                "budget_balance": budget_balance,
                "income": monthly_income,
                "expenses": behaviour_expense,
            }
        )

    return {
        "rows": rows,
        "has_enough_history": True,
        "has_recurring_data": bool(streams),
        "months_of_history": len(months),
        "starting_balance": float(starting),
    }
