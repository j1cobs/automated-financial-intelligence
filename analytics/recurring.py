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
from itertools import pairwise
from typing import Any

import pandas as pd

from analytics.categorizer import merchant_key

__all__ = [
    "CADENCE_ANNUALLY",
    "CADENCE_BIWEEKLY",
    "CADENCE_MONTHLY",
    "CADENCE_UNKNOWN",
    "CADENCE_WEEKLY",
    "CADENCE_DAYS",
    "cadence_from_days",
    "derive_streams",
    "predict_next_date",
    "resolve_is_recurring",
    "upcoming_from_streams",
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
        merchant_key(row.merchant_name, str(row.description or "")) for row in working.itertuples(index=False)
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

        gaps = [(later - earlier).days for earlier, later in pairwise(occurrence_dates)]
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
                "status": ("mature" if len(occurrence_dates) >= _MATURE_OCCURRENCES else "early_detection"),
                "source": "local",
                "is_active": True,
            }
        )

    return streams


#: Nominal length of each cadence, for turning a cadence back into a gap.
CADENCE_DAYS: dict[str, int] = {
    CADENCE_WEEKLY: 7,
    CADENCE_BIWEEKLY: 14,
    CADENCE_MONTHLY: 30,
    CADENCE_ANNUALLY: 365,
}


def resolve_is_recurring(
    user_flag: bool | None,
    in_stream: bool,
) -> bool:
    """Whether a transaction reads as recurring.

    Precedence, matching the rule `user_category` and `is_duplicate` already
    follow: **a user decision always wins**. The pipeline never clears a flag
    the user set by hand, so a charge they marked stays marked even when no
    stream matches it (Plaid missed it, or it is from a non-Plaid source).

        1. user override (`transactions.is_recurring` set by hand)
        2. stream membership
        3. not recurring

    `user_flag` is None for rows ingested before the flag existed; that means
    "unknown", not False, so it falls through to stream membership.
    """
    if user_flag:
        return True
    return bool(in_stream)


def upcoming_from_streams(
    streams: list[dict[str, Any]],
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Upcoming charges, one entry per stream, soonest first.

    Deduplicated by construction: the old path grouped by raw description, so
    the same charge could appear several times under near-identical strings.
    A stream is already the deduplicated unit.

    Only outflows are returned -- "Upcoming Recurring Charges" is about money
    leaving, and mixing payroll into it made the card read as though income
    were a bill. Streams with no predicted date are skipped rather than shown
    with a blank.
    """
    reference = today or date.today()
    rows: list[dict[str, Any]] = []

    for stream in streams:
        if not stream.get("is_active", True):
            continue
        if stream.get("direction") != "outflow":
            continue

        next_date = stream.get("predicted_next_date")
        if next_date is None:
            continue
        if isinstance(next_date, str):
            next_date = date.fromisoformat(next_date)

        # A prediction that has already passed means the charge is late or was
        # missed. Roll it forward by whole cadences so the card shows the next
        # date that is actually in the future, rather than a stale one.
        gap = CADENCE_DAYS.get(stream.get("cadence") or "", 0)
        if gap > 0:
            while next_date < reference:
                next_date = next_date + timedelta(days=gap)
        elif next_date < reference:
            continue

        rows.append(
            {
                "description": stream.get("description") or stream.get("merchant_key") or "",
                "amount": abs(float(stream.get("last_amount") or 0.0)),
                "next_expected_date": next_date.strftime("%Y-%m-%d"),
                "typical_interval_days": gap or None,
                "status": stream.get("status"),
                "stream_id": stream.get("stream_id"),
            }
        )

    rows.sort(key=lambda row: row["next_expected_date"])
    return rows
