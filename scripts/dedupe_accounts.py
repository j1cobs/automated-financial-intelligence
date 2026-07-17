"""One-off cleanup for accounts duplicated by a Plaid Item re-link (e.g. after rotating
access tokens): the same physical account gets a new account_id, and therefore a new
account_key, so it lands as a second `accounts` row with its own parallel transaction history
instead of continuing the original one.

Groups existing accounts by persistent_account_id (Plaid's stable cross-relink identifier)
first, falling back to an exact match on (mask, official_name, account_subtype, owner_name)
for rows that predate that column. Within each group, the oldest account_key is kept as
canonical; every other account_key in the group has its transactions reassigned onto the
canonical key and is then deleted. Finally, all transaction_hash values are recomputed (the
hash now keys off account_key instead of the fragile, occasionally-empty account_name), and
any two transactions that collide under the new formula — the same real transaction inserted
twice under different account_keys — are merged, keeping the earliest row.

Usage:
    python scripts/dedupe_accounts.py            # dry run: report only, no writes
    python scripts/dedupe_accounts.py --apply    # perform the merge + rehash
"""

from __future__ import annotations

import argparse
import logging
from collections import defaultdict

import psycopg

from core.config import load_settings
from database.db import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)


def _fetch_accounts(database_url: str) -> list[dict]:
    sql = (
        "SELECT account_key, persistent_account_id, mask, official_name, "
        "account_subtype, owner_name, created_at FROM accounts ORDER BY created_at"
    )
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def _group_duplicates(accounts: list[dict]) -> list[list[dict]]:
    by_persistent_id: dict[str, list[dict]] = defaultdict(list)
    by_heuristic: dict[tuple, list[dict]] = defaultdict(list)
    unmatched: list[dict] = []

    for account in accounts:
        if account["persistent_account_id"]:
            by_persistent_id[account["persistent_account_id"]].append(account)
        elif all(
            account[field]
            for field in ("mask", "official_name", "account_subtype", "owner_name")
        ):
            key = (
                account["mask"],
                account["official_name"],
                account["account_subtype"],
                account["owner_name"],
            )
            by_heuristic[key].append(account)
        else:
            unmatched.append(account)

    groups = [g for g in by_persistent_id.values() if len(g) > 1]
    groups += [g for g in by_heuristic.values() if len(g) > 1]
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Perform the merge and rehash (default: dry run)"
    )
    args = parser.parse_args()

    settings = load_settings()
    database = DatabaseClient(settings.database_url)
    accounts = _fetch_accounts(settings.database_url)
    groups = _group_duplicates(accounts)

    if not groups:
        LOGGER.info("No duplicate accounts found.")
        return

    total_moved = 0
    for group in groups:
        group_sorted = sorted(group, key=lambda a: a["created_at"])
        canonical = group_sorted[0]
        duplicates = group_sorted[1:]
        LOGGER.info(
            "Group: canonical=%s (created %s); duplicates=%s",
            canonical["account_key"],
            canonical["created_at"],
            [d["account_key"] for d in duplicates],
        )
        for duplicate in duplicates:
            if args.apply:
                moved = database.merge_account(
                    duplicate["account_key"], canonical["account_key"]
                )
                total_moved += moved
                LOGGER.info(
                    "  merged %s -> %s (%d transactions reassigned)",
                    duplicate["account_key"],
                    canonical["account_key"],
                    moved,
                )
            else:
                LOGGER.info(
                    "  [dry run] would merge %s -> %s",
                    duplicate["account_key"],
                    canonical["account_key"],
                )

    if not args.apply:
        LOGGER.info("Dry run complete. Re-run with --apply to perform the merge.")
        return

    LOGGER.info("Merged %d accounts, %d transactions reassigned. Rehashing transactions...",
                sum(len(g) - 1 for g in groups), total_moved)
    rehashed, deleted = database.rehash_transactions()
    LOGGER.info(
        "Rehash complete: %d transaction_hash values updated, %d duplicate transactions removed.",
        rehashed,
        deleted,
    )


if __name__ == "__main__":
    main()
