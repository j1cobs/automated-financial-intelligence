"""Generic savings goals (Phase 33).

Nothing here knows what a house is. A down payment, a car, an emergency fund and
a retirement pot are the same shape: a target amount, an optional target date, a
set of accounts that hold the money, and a baseline captured when the goal
started. The property purchase that prompted the feature is just one instance.

Two decisions are load-bearing:

**Progress is measured from account balances, not cash flow.** Cumulative
(income − expenses) needs no setup and counts every dollar not spent, but it
drifts from reality the moment money moves somewhere the dashboard cannot see,
and it keeps counting money that was later spent. Linked balances minus a
baseline cannot lie in that way.

**A pace is never surfaced without its basis.** `account_balance_snapshots` only
began collecting around 2026-08-25, so balance-derived growth has thin history.
Below `BALANCE_BASIS_MIN_WEEKS` the honest answer is a cash-flow figure that says
so. The switch is hard, not a blend: one number with one stated provenance beats
a weighted figure nobody can reconstruct by looking at it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

__all__ = [
    "BALANCE_BASIS_MIN_WEEKS",
    "BASIS_BALANCE",
    "BASIS_CASHFLOW",
    "contested_amounts",
    "pace",
    "progress",
    "projection",
    "what_if",
]

BASIS_BALANCE = "balance"
BASIS_CASHFLOW = "cashflow"

#: Weeks of balance history required before pace is derived from balances
#: rather than cash flow.
BALANCE_BASIS_MIN_WEEKS = 12

#: Average days per month, for converting a growth rate into a monthly figure.
_DAYS_PER_MONTH = 30.44


def _linked_balance(goal: dict[str, Any], balances: dict[str, float]) -> float:
    return sum(float(balances.get(key, 0.0)) for key in goal.get("account_keys", []))


def progress(goal: dict[str, Any], balances: dict[str, float]) -> float:
    """Amount saved toward `goal`: linked balances minus the goal's baseline.

    Deliberately **not** floored at zero. If the balance has fallen below the
    baseline the user has spent goal money, and hiding that behind a 0 would
    misrepresent exactly the situation they most need to see.
    """
    return _linked_balance(goal, balances) - float(goal.get("baseline_amount") or 0.0)


def pace(
    goal: dict[str, Any],
    snapshots: list[dict[str, Any]],
    cashflow_monthly: float,
) -> tuple[float, str, int]:
    """`(amount_per_month, basis, weeks_of_history)`.

    `snapshots` is the combined balance of the goal's linked accounts over time,
    as `{snapshot_date, balance}` rows. With at least `BALANCE_BASIS_MIN_WEEKS`
    of them, the pace is measured growth; below that it is `cashflow_monthly`,
    reported as such.

    The caller must surface `basis` and `weeks_of_history` alongside the number.
    A confident-looking pace built on four weeks is worse than no pace at all.
    """
    ordered = sorted(snapshots, key=lambda row: row["snapshot_date"])
    if len(ordered) < 2:
        return float(cashflow_monthly), BASIS_CASHFLOW, 0

    first, last = ordered[0], ordered[-1]
    span_days = (last["snapshot_date"] - first["snapshot_date"]).days
    weeks = span_days // 7

    if weeks < BALANCE_BASIS_MIN_WEEKS or span_days <= 0:
        return float(cashflow_monthly), BASIS_CASHFLOW, weeks

    growth = float(last["balance"]) - float(first["balance"])
    months = span_days / _DAYS_PER_MONTH
    return growth / months, BASIS_BALANCE, weeks


def projection(
    goal: dict[str, Any],
    saved: float,
    monthly_pace: float,
    today: date | None = None,
) -> dict[str, Any]:
    """When this goal lands at the given pace, and whether that beats its target.

    `projected_date` is None when the pace is zero or negative — dividing by it
    would produce infinity, not a date. `on_track` is None when there is nothing
    to be on track *against* (no target date) or no projection to compare.
    """
    reference = today or date.today()
    target = float(goal.get("target_amount") or 0.0)
    remaining = max(target - saved, 0.0)

    if remaining <= 0:
        return {
            "remaining": 0.0,
            "projected_date": None,
            "on_track": True,
            "is_complete": True,
            "months_remaining": 0.0,
        }

    if monthly_pace <= 0:
        return {
            "remaining": remaining,
            "projected_date": None,
            "on_track": None,
            "is_complete": False,
            "months_remaining": None,
        }

    months_remaining = remaining / monthly_pace
    projected = reference + timedelta(days=round(months_remaining * _DAYS_PER_MONTH))

    target_date = goal.get("target_date")
    on_track = None if target_date is None else projected <= target_date

    return {
        "remaining": remaining,
        "projected_date": projected,
        "on_track": on_track,
        "is_complete": False,
        "months_remaining": months_remaining,
    }


def what_if(
    goal: dict[str, Any],
    saved: float,
    monthly_pace: float,
    monthly_reduction: float,
    today: date | None = None,
) -> dict[str, Any]:
    """`projection` with `monthly_reduction` more going in each month.

    This is what makes the tracker actionable rather than decorative: "cut
    dining by $200 and you hit the target in February instead of April" is a
    decision, where a progress bar is only a status.
    """
    return projection(
        goal,
        saved=saved,
        monthly_pace=monthly_pace + max(float(monthly_reduction), 0.0),
        today=today,
    )


def contested_amounts(
    goals: list[dict[str, Any]],
    balances: dict[str, float],
) -> dict[Any, float]:
    """Per goal id, how much of its balance sits in an account another goal also claims.

    Overlap is permitted because it reflects how people actually save — one
    savings account backing both a down payment and an emergency fund. But it
    must be visible, or the dashboard reports two goals on track when the same
    dollars can only buy one of them.
    """
    claims: dict[str, int] = {}
    for goal in goals:
        for key in goal.get("account_keys", []):
            claims[key] = claims.get(key, 0) + 1

    contested: dict[Any, float] = {}
    for goal in goals:
        shared = sum(
            float(balances.get(key, 0.0)) for key in goal.get("account_keys", []) if claims.get(key, 0) > 1
        )
        contested[goal["id"]] = shared
    return contested
