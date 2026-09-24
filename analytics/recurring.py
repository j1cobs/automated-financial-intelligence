"""Derive recurring streams from our own transaction history (Phase 30).

This is the fallback for when Plaid's recurring-transactions add-on is not
entitled on the account. `PlaidIngestor.fetch_recurring_streams()` is preferred
when it is available — Plaid sees more history than our 90-day window and does
the grouping itself — but both paths emit rows of **exactly the same shape**, so
persistence, the API and the UI are indifferent to which one produced them.

The detection is deliberately strict. A stream asserts "this will happen again,
around then, for about this much"; a false positive puts a charge on the user's
Upcoming list that never arrives. So:

  - two occurrences minimum, and fewer than three is `early_detection` rather
    than `mature`, matching Plaid's own threshold;
  - the gaps must actually look periodic (see `cadence_from_days`), so three
    visits to the same shop at random intervals produce nothing;
  - an unrecognised gap yields `UNKNOWN` and the group is dropped rather than
    having a cadence invented for it.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Any

import pandas as pd

from analytics.categorizer import merchant_key

__all__ = [
    "CADENCE_ANNUALLY",
    "CADENCE_BIWEEKLY",
    "CADENCE_MONTHLY",
    "CADENCE_UNKNOWN",
    "CADENCE_WEEKLY",
    "cadence_from_days",
    "derive_streams",
    "predict_next_date",
]

CADENCE_WEEKLY = "WEEKLY"
CADENCE_BIWEEKLY = "BIWEEKLY"
CADENCE_MONTHLY = "MONTHLY"
CADENCE_ANNUALLY = "ANNUALLY"
CADENCE_UNKNOWN = "UNKNOWN"

#: (low, high, label) in days, inclusive. The windows are wide enough for real
#: billing drift -- a "monthly" charge lands anywhere from the 28th to the 3rd --
#: but never overlap, so a gap maps to at most one cadence.
_CADENCE_WINDOWS: tuple[tuple[int, int, str], ...] = (
    (6, 8, CADENCE_WEEKLY),
    (13, 16, CADENCE_BIWEEKLY),
    (27, 34, CADENCE_MONTHLY),
    (350, 380, CADENCE_ANNUALLY),
)

#: Below this many occurrences Plaid reports a stream as `early_detection`.
_MATURE_OCCURRENCES = 3


def cadence_from_days(days: float) -> str:
    """Label a typical inter-occurrence gap, or UNKNOWN if it fits no window."""
    if days <= 0:
        return CADENCE_UNKNOWN
    for low, high, label in _CADENCE_WINDOWS:
        if low <= days <= high:
            return label
    return CADENCE_UNKNOWN


def predict_next_date(last: date | None, median_gap_days: float) -> date | None:
    """The next expected occurrence, or None when there is no usable gap."""
    if last is None or median_gap_days <= 0:
        return None
    return last + timedelta(days=int(round(median_gap_days)))


def derive_streams(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Group `frame` into recurring streams.

    `frame` needs `date`, `description`, `amount`, and optionally
    `merchant_name` and `category`. Returns one dict per detected stream, in the
    same shape as the Plaid path.
    """
    if frame is None or frame.empty:
        return []

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    working = working.dropna(subset=["date"])
    if working.empty:
        return []

    if "merchant_name" not in working.columns:
        working["merchant_name"] = None
    if "category" not in working.columns:
        working["category"] = None

    working["_key"] = [
        merchant_key(row.merchant_name, str(row.description or ""))
        for row in working.itertuples(index=False)
    ]

    streams: list[dict[str, Any]] = []
    for key, group in working.groupby("_key", sort=True):
        if not key:
            continue

        ordered = group.sort_values("date")
        occurrence_dates = [value.date() for value in ordered["date"]]
        if len(occurrence_dates) < 2:
            # One charge carries no cadence. Inventing one would produce a
            # stream that cannot predict anything.
            continue

        gaps = [
            (later - earlier).days
            for earlier, later in zip(occurrence_dates, occurrence_dates[1:])
        ]
        median_gap = statistics.median(gaps)
        cadence = cadence_from_days(median_gap)
        if cadence == CADENCE_UNKNOWN:
            # Irregular spending at a merchant is not a subscription.
            continue

        last_row = ordered.iloc[-1]
        last_amount = float(last_row["amount"])
        last_date = occurrence_dates[-1]

        streams.append(
            {
                "stream_id": f"local:{key}",
                "merchant_key": key,
                "description": str(last_row["description"] or key),
                "category": last_row["category"] if pd.notna(last_row["category"]) else None,
                "cadence": cadence,
                # Sign convention matches the rest of the pipeline: a negative
                # amount leaves the account.
                "direction": "outflow" if last_amount < 0 else "inflow",
                "last_amount": last_amount,
                "last_date": last_date,
                "predicted_next_date": predict_next_date(last_date, median_gap),
                "status": (
                    "mature"
                    if len(occurrence_dates) >= _MATURE_OCCURRENCES
                    else "early_detection"
                ),
                "source": "local",
                "is_active": True,
            }
        )

    return streams
