"""Cached loading of the dashboard's transaction/account frames.

PLAN.md Phase 15, Fix 15. `load_financial_data` runs an unbounded
`SELECT ... ORDER BY transaction_date DESC` and `prepare_transactions` then enriches the
whole frame — transfer pair-matching included. Every read endpoint did both, per request,
so one dashboard load paid for it five times over (six, now that the Budget tab sources
its sparklines from `/cash-flow`), and every ledger edit paid for it again.

The pipeline writes once a day, so a short TTL is close to free: within the window every
endpoint on a page load shares one read.

**Why this is a cache and not a bounded query.** The obvious fix is to push the date
window into SQL, but `load_financial_data` lives in `app/dashboard.py`, which Phase 15
freezes. The alternatives were duplicating the schema into a second query (a worse trade
than this) or unfreezing that function. This wraps the frozen loader instead. If read
latency ever justifies it, the right move is to relocate `load_financial_data` into
`database/` — it is a data-access function that happens to live in the Streamlit module —
rather than to add a second copy of the query.

**Writes must invalidate.** Every write endpoint calls `invalidate(...)`. Without it, a
category edit would return 204, the frontend would refetch, and the API would serve the
pre-edit rows straight back out of this cache for up to a minute — the edit would appear
to silently fail. That is the whole reason `invalidate` exists; do not drop those calls.
"""

from __future__ import annotations

import threading
import time

import pandas as pd

from app.dashboard import load_financial_data

from .viewmodels import prepare_transactions

CACHE_TTL_SECONDS = 60.0

_lock = threading.Lock()
_cache: dict[str, tuple[float, pd.DataFrame, pd.DataFrame]] = {}


def load_frames(database_url: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """`(enriched_transactions, accounts)`, memoised per database URL for `CACHE_TTL_SECONDS`.

    Callers must treat the returned frames as READ-ONLY. They are shared between requests
    for the lifetime of the entry, so mutating one in place would corrupt every later
    reader. Every builder in `api/viewmodels.py` already copies before mutating, and
    `api/filters.py` masks (which allocates); `tests/test_api_dataload.py` pins that.
    """
    now = time.monotonic()
    with _lock:
        entry = _cache.get(database_url)
        if entry is not None and now - entry[0] < CACHE_TTL_SECONDS:
            return entry[1], entry[2]

    # Deliberately outside the lock: a slow query shouldn't block every other request.
    # Two concurrent misses may both load — wasteful once, never wrong, and far better
    # than serialising every reader behind one database round-trip.
    tx_df, acct_df = load_financial_data(database_url)
    prepared = prepare_transactions(tx_df)

    with _lock:
        _cache[database_url] = (time.monotonic(), prepared, acct_df)
    return prepared, acct_df


def invalidate(database_url: str) -> None:
    """Drop the cached frames for one database. Called by every write endpoint."""
    with _lock:
        _cache.pop(database_url, None)


def clear() -> None:
    """Drop everything. For tests and for process-wide resets."""
    with _lock:
        _cache.clear()
