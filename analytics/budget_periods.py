"""Per-month budget caps with carry-forward inheritance (Phase 28).

`budget_periods` stores only the months a cap was *explicitly* set in. Every
other month inherits the most recent explicit cap before it, so setting a cap
once holds it until it is changed — without writing a row per category per
month, and without a later edit rewriting history.

Everything here is pure and DB-free: `resolve_caps` takes the rows and answers
for one period. That keeps the inheritance rule unit-testable without a
database, which matters because the rule is easy to get subtly wrong.

**Absent is not zero.** A category with no explicit cap at or before the
requested period is simply missing from the result. A category capped at `0` is
present with a value of `0`. "No budget set" and "budgeted to spend nothing"
are different states and must render differently; conflating them would make
every uncapped category look instantly over budget.
"""

from __future__ import annotations

import re
from decimal import Decimal

__all__ = [
    "PERIOD_PATTERN",
    "next_period",
    "previous_period",
    "resolve_caps",
    "resolve_caps_detailed",
]

PERIOD_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def _parse_period(period: str) -> tuple[int, int]:
    match = PERIOD_PATTERN.match(period or "")
    if not match:
        raise ValueError(f"period must be 'YYYY-MM', got {period!r}")
    return int(match.group(1)), int(match.group(2))


def previous_period(period: str) -> str:
    """The calendar month before `period`, wrapping across the year boundary."""
    year, month = _parse_period(period)
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def next_period(period: str) -> str:
    """The calendar month after `period`, wrapping across the year boundary."""
    year, month = _parse_period(period)
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def resolve_caps_detailed(rows: list[dict], period: str) -> dict[str, tuple[Decimal, str]]:
    """As `resolve_caps`, but each value is `(limit, source_period)`.

    `source_period` is the month the cap was actually set in — equal to
    `period` when the cap is explicit, earlier when it is inherited. The UI
    needs it to say "inherited from August" rather than presenting an
    inherited cap as though it had been set for the month on screen.
    """
    _parse_period(period)

    # Compared as strings on purpose: zero-padded 'YYYY-MM' sorts
    # chronologically under plain lexicographic comparison, so no date parsing
    # is needed to find "the most recent row at or before this period".
    best: dict[str, tuple[str, Decimal]] = {}
    for entry in rows:
        row_period = entry["period"]
        if row_period > period:
            continue  # a later edit must not leak backwards into this month
        category = entry["category"]
        current = best.get(category)
        if current is None or row_period > current[0]:
            best[category] = (row_period, Decimal(str(entry["monthly_limit"])))

    return {category: (limit, source_period) for category, (source_period, limit) in best.items()}


def resolve_caps(rows: list[dict], period: str) -> dict[str, Decimal]:
    """Cap for each category in `period`.

    For each category: the explicit row for that period, else the most recent
    explicit row strictly before it. Categories whose first explicit cap falls
    *after* `period` are absent from the result — never coerced to 0.

    `rows` is whatever `DatabaseClient.get_budget_periods()` returned; order is
    irrelevant. `monthly_limit` may be a float, Decimal, int or numeric string.
    """
    return {category: limit for category, (limit, _) in resolve_caps_detailed(rows, period).items()}
