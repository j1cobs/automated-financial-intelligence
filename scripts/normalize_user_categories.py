"""Normalise free-text `transactions.user_category` values onto the canonical set.

Phase 28c closed the category set: `PATCH /transactions/{hash}/category` now
only accepts values `analytics.categories.canonicalize` can map. Corrections
made *before* that, though, may hold anything that was ever typed — and budget
caps are keyed on category, so a stray value means a budget row nothing can
ever match.

This is a script, not a migration, on purpose. `ensure_schema()` re-runs every
`.sql` on every call; a migration that rewrites `user_category` would re-run
against live data on every pipeline run forever, and the blast radius of a
mistake there is every correction the user has ever made.

**Unmappable values are reported, never rewritten and never flattened to
OTHER.** A value this script cannot map unambiguously is one a human should
look at: the mapping is conservative by design, and guessing would silently
destroy what the correction meant.

Usage:
    python scripts/normalize_user_categories.py            # report only, no writes
    python scripts/normalize_user_categories.py --apply    # rewrite the mappable ones
"""

from __future__ import annotations

import argparse
import logging

import psycopg

from analytics.categories import canonicalize
from core.config import load_settings
from database.db import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)


def distinct_user_categories(db: DatabaseClient) -> list[tuple[str, int]]:
    """Every distinct non-null `user_category`, with how many rows carry it."""
    sql = """
    SELECT user_category, COUNT(*)
    FROM transactions
    WHERE user_category IS NOT NULL
    GROUP BY user_category
    ORDER BY COUNT(*) DESC, user_category
    """
    with psycopg.connect(db.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [(row[0], row[1]) for row in cur.fetchall()]


def rewrite(db: DatabaseClient, old: str, new: str) -> int:
    """Point every row carrying `old` at `new`. Returns rows affected."""
    sql = "UPDATE transactions SET user_category = %s WHERE user_category = %s"
    with psycopg.connect(db.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (new, old))
            affected = cur.rowcount
        conn.commit()
    return affected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the rewrite (default: dry run)")
    args = parser.parse_args()

    settings = load_settings()
    db = DatabaseClient(settings.database_url)

    values = distinct_user_categories(db)
    if not values:
        LOGGER.info("No user_category corrections found; nothing to do.")
        return 0

    already_canonical: list[tuple[str, int]] = []
    mappable: list[tuple[str, str, int]] = []
    unmappable: list[tuple[str, int]] = []

    for value, count in values:
        target = canonicalize(value)
        if target is None:
            unmappable.append((value, count))
        elif target == value:
            already_canonical.append((value, count))
        else:
            mappable.append((value, target, count))

    LOGGER.info(
        "%d distinct correction values: %d already canonical, %d mappable, %d unmappable.",
        len(values),
        len(already_canonical),
        len(mappable),
        len(unmappable),
    )

    for value, target, count in mappable:
        LOGGER.info("  map    %r -> %s  (%d rows)", value, target, count)

    for value, count in unmappable:
        LOGGER.warning("  SKIP   %r  (%d rows) -- no unambiguous mapping", value, count)

    if unmappable:
        LOGGER.warning(
            "%d value(s) left untouched. Recategorize those transactions in the "
            "dashboard; this script will not guess on your behalf.",
            len(unmappable),
        )

    if not mappable:
        LOGGER.info("Nothing to rewrite.")
        return 0

    if not args.apply:
        LOGGER.info("Dry run -- no changes written. Re-run with --apply to rewrite.")
        return 0

    total = 0
    for value, target, _count in mappable:
        total += rewrite(db, value, target)
    LOGGER.info("Rewrote %d row(s).", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
