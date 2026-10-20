"""Explainable anomaly detection (Phase 34).

Replaces `analytics/outlier_detector.py`, an Isolation Forest that was written
in Phase 1 and never wired up. It was retired rather than activated, for three
reasons:

  - its score cannot be explained — "this transaction scores 0.83" is not
    something a person can act on;
  - it is unsupervised with a fixed `contamination=0.03`, so it flags about 3%
    of rows no matter how ordinary the month was; and
  - on personal finance it converges on permanently flagging rent and large
    legitimate purchases, which is noise with extra steps.

What replaces it is two deterministic rules that each produce a sentence:

  **Category drift** — this category is spending well above its own recent
  baseline. Scored by **MAD** (median absolute deviation) rather than standard
  deviation, so one freak month cannot inflate the spread and mask a genuine
  overspend the month after. Compared **at the same day of the month**, never
  projected to end-of-month: extrapolating from day 2 turns a single ordinary
  purchase into a ~15x projection and would fire an alert every month.

  **Price creep** — a recurring charge's amount changed. Dual percent-and-
  dollar threshold, because either alone misfires: 20% of a $2 charge is 40
  cents, and $4 on a $400 charge is 1%.

Where learning belongs is the feedback loop, not a model: a dismissed alert
stays dismissed **for that period**. See `suppress_dismissed`. This mirrors
Phase 18's categorizer, where `merchant_categories` is a user-correction
memory feeding a deterministic cascade.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Any

import pandas as pd

from analytics.categorizer import merchant_key

__all__ = [
    "KIND_CATEGORY_DRIFT",
    "KIND_PRICE_CREEP",
    "MIN_MONTHS_OF_HISTORY",
    "SEVERITY_HIGH",
    "SEVERITY_MEDIUM",
    "detect_anomalies",
    "detect_category_drift",
    "detect_price_creep",
    "suppress_dismissed",
]

KIND_CATEGORY_DRIFT = "category_drift"
KIND_PRICE_CREEP = "price_creep"

SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

#: Complete prior months required before any anomaly is emitted. A median over
#: two months presented as a baseline is a number that looks more authoritative
#: than it is -- and `days_back` defaults to 90, so thin history is the normal
#: case early on, not an edge case.
MIN_MONTHS_OF_HISTORY = 3

#: Drift thresholds, in MADs above the baseline.
_DRIFT_MEDIUM_MADS = 2.5
_DRIFT_HIGH_MADS = 4.0

#: Price-creep thresholds. BOTH the percentage and the dollar figure must be
#: exceeded for a given severity, which is what suppresses small-stream noise
#: and large-stream rounding alike.
_CREEP_MEDIUM_PCT, _CREEP_MEDIUM_ABS = 0.10, 3.0
_CREEP_HIGH_PCT, _CREEP_HIGH_ABS = 0.25, 15.0

#: MAD of a perfectly steady history is 0, which would make any increase
#: infinitely many MADs. Fall back to a fraction of the median so "steady
#: history, small wobble" doesn't alert.
_MIN_SPREAD_FRACTION = 0.15


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _mad(values: list[float], median: float) -> float:
    """Median absolute deviation. Robust: unaffected by a single freak value."""
    if not values:
        return 0.0
    return statistics.median([abs(value - median) for value in values])


def detect_category_drift(
    frame: pd.DataFrame,
    period: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Flag categories spending well above their own same-day-of-month baseline.

    `frame` must be enriched (`month`, `tx_type`, `category`, `adjusted_amount`)
    and duplicate-excluded. `period` is the month under examination.
    """
    if frame is None or frame.empty:
        return []
    required = {"month", "tx_type", "category", "adjusted_amount", "date"}
    if not required.issubset(frame.columns):
        return []

    reference = today or date.today()
    day_of_month = reference.day

    expenses = frame[frame["tx_type"] == "expense"].copy()
    if expenses.empty:
        return []
    expenses["_day"] = pd.to_datetime(expenses["date"]).dt.day

    # Everything is compared "by day N", so a partial current month is measured
    # against the same slice of each prior month rather than its full total.
    to_date = expenses[expenses["_day"] <= day_of_month]

    current = to_date[to_date["month"] == period]
    prior = to_date[to_date["month"] < period]
    if prior.empty:
        return []

    found: list[dict[str, Any]] = []
    for category, current_rows in current.groupby("category"):
        spent = float(current_rows["adjusted_amount"].sum().__abs__())
        if spent <= 0:
            continue

        history = prior[prior["category"] == category]
        if history.empty:
            continue

        by_month = history.groupby("month")["adjusted_amount"].sum().abs()
        baselines = [float(value) for value in by_month.tolist()]
        if len(baselines) < MIN_MONTHS_OF_HISTORY:
            continue

        median = statistics.median(baselines)
        if median <= 0:
            continue

        spread = max(_mad(baselines, median), median * _MIN_SPREAD_FRACTION)
        excess = spent - median
        if excess <= 0:
            # Spending less than usual is not something to alert on: this is a
            # budget-drift detector, not a change detector.
            continue

        mads = excess / spread
        if mads >= _DRIFT_HIGH_MADS:
            severity = SEVERITY_HIGH
        elif mads >= _DRIFT_MEDIUM_MADS:
            severity = SEVERITY_MEDIUM
        else:
            continue

        pct = excess / median
        found.append(
            {
                "kind": KIND_CATEGORY_DRIFT,
                "subject": str(category),
                "period": period,
                "severity": severity,
                "explanation": (
                    f"{category} is {_money(spent)} so far, "
                    f"{pct:.0%} above your usual {_money(median)} by day {day_of_month} "
                    f"(based on {len(baselines)} month{'s' if len(baselines) != 1 else ''})."
                ),
                # These rows feed the `is_outlier` flags, so the outliers view has
                # something relevant to show.
                "contributing_hashes": _top_contributors(current_rows),
            }
        )

    found.sort(key=lambda row: row["subject"])
    return found


def _top_contributors(rows: pd.DataFrame, limit: int = 3) -> list[str]:
    if "transaction_hash" not in rows.columns:
        return []
    ordered = rows.reindex(rows["adjusted_amount"].abs().sort_values(ascending=False).index)
    return [str(value) for value in ordered["transaction_hash"].head(limit).tolist()]


def detect_price_creep(
    frame: pd.DataFrame,
    streams: list[dict[str, Any]],
    period: str,
) -> list[dict[str, Any]]:
    """Flag recurring charges whose amount has changed materially.

    Compares each stream's most recent amount against the median of its earlier
    occurrences (median, so one odd month -- a prorated first bill, a one-off
    surcharge -- doesn't read as a permanent price change).
    """
    if frame is None or frame.empty or not streams:
        return []
    if "adjusted_amount" not in frame.columns or "description" not in frame.columns:
        return []

    working = frame.copy()
    if "merchant_name" not in working.columns:
        working["merchant_name"] = None
    working["_key"] = [
        merchant_key(row.merchant_name, str(row.description or "")) for row in working.itertuples(index=False)
    ]

    found: list[dict[str, Any]] = []
    for stream in streams:
        if stream.get("direction") != "outflow":
            continue
        key = stream.get("merchant_key")
        if not key:
            continue

        group = working[working["_key"] == key]
        if len(group) < 2:
            continue

        ordered = group.sort_values("date")

        # The change must have happened IN `period`. Without this the latest
        # occurrence is whenever it happened, compared against everything
        # before it, and then stamped with the current month -- so a price rise
        # six months ago produces a fresh, undismissed anomaly every month
        # thereafter, each with identical text.
        if "month" in ordered.columns:
            if str(ordered["month"].iloc[-1]) != period:
                continue
        else:
            last_date = pd.to_datetime(ordered["date"].iloc[-1])
            if last_date.strftime("%Y-%m") != period:
                continue

        amounts = [abs(float(value)) for value in ordered["adjusted_amount"].tolist()]
        latest = amounts[-1]
        previous = amounts[:-1]
        baseline = statistics.median(previous)
        if baseline <= 0:
            continue

        delta = latest - baseline
        if delta <= 0:
            # A price going down is not something to alert on.
            continue

        pct = delta / baseline
        if pct >= _CREEP_HIGH_PCT and delta >= _CREEP_HIGH_ABS:
            severity = SEVERITY_HIGH
        elif pct >= _CREEP_MEDIUM_PCT and delta >= _CREEP_MEDIUM_ABS:
            severity = SEVERITY_MEDIUM
        else:
            continue

        description = stream.get("description") or key
        found.append(
            {
                "kind": KIND_PRICE_CREEP,
                "subject": str(stream.get("stream_id") or key),
                "period": period,
                "severity": severity,
                "explanation": (
                    f"{description} went from {_money(baseline)} to {_money(latest)} ({pct:.0%} more)."
                ),
                "contributing_hashes": (
                    [str(ordered["transaction_hash"].iloc[-1])]
                    if "transaction_hash" in ordered.columns
                    else []
                ),
            }
        )

    found.sort(key=lambda row: row["subject"])
    return found


def suppress_dismissed(
    anomalies: list[dict[str, Any]],
    dismissed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop anomalies the user has dismissed **for that period**.

    Period-scoped on purpose. Dismissing September's Dining drift because of a
    birthday must not silence October's — an alert that never comes back is an
    alert that goes quiet exactly as it becomes useful. A category dismissed
    twelve months running is itself telling you the cap is wrong.
    """
    if not dismissed:
        return list(anomalies)
    blocked = {(row["kind"], row["subject"], row["period"]) for row in dismissed}
    return [a for a in anomalies if (a["kind"], a["subject"], a["period"]) not in blocked]


def detect_anomalies(
    frame: pd.DataFrame,
    streams: list[dict[str, Any]],
    period: str,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Run every detector for `period`. Deterministic: the same inputs give the
    same rows, which is what makes `UNIQUE (kind, subject, period)` persistence
    idempotent across pipeline runs."""
    return [
        *detect_category_drift(frame, period, today=today),
        *detect_price_creep(frame, streams, period),
    ]
