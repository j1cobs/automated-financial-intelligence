"""One-off cleanup for accounts duplicated by a Plaid Item re-link (e.g. after rotating
access tokens): the same physical account gets a new account_id, and therefore a new
account_key, so it lands as a second `accounts` row with its own parallel transaction history
instead of continuing the original one.

Groups existing accounts by persistent_account_id (Plaid's stable cross-relink identifier)
first, falling back to an exact match on (official_name, account_subtype, account_type),
partitioned by mask where more than one distinct mask is present. `owner_name` is deliberately
excluded from identity: it records which connection/token revealed the account, not who owns
it, so a jointly-held account visible through two tokens would otherwise bucket separately and
never merge. Within each group, the account_key Plaid is still syncing (most recently updated,
tie-broken by having a known mask, then by newest created_at) is kept as canonical — not the
oldest — since an orphaned key that Plaid no longer issues would otherwise get re-created as a
duplicate again on the very next pipeline run. Every other account_key in the group has its
transactions reassigned onto the canonical key and is then deleted. Finally, all
transaction_hash values are recomputed (the hash now keys off account_key instead of the
fragile, occasionally-empty account_name), and any two transactions that collide under the new
formula — the same real transaction inserted twice under different account_keys — are merged,
keeping the earliest row.

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
        "account_type, account_subtype, owner_name, created_at, updated_at "
        "FROM accounts ORDER BY updated_at"
    )
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [desc.name for desc in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _group_duplicates(accounts: list[dict]) -> list[list[dict]]:
    """Group accounts that represent the same physical account under different account_keys.

    Primary signal: persistent_account_id (Plaid's stable cross-relink identifier). Rows
    without it (e.g. inserted before that column existed, or from an institution that doesn't
    support it) fall back to an exact match on (official_name, account_subtype, account_type)
    — deliberately excluding both `mask` and `owner_name` from the bucket key itself. `mask` is
    excluded because rows that predate the `mask` column have it as NULL and NULL never equals
    another value, which would silently hide exactly the historical duplicates this script
    exists to find. `owner_name` is excluded because it records which connection/token revealed
    the account, not who owns it — keeping it in the key would prevent a jointly-held account
    seen through two different tokens from ever being recognised as the same account.

    A single (official_name, account_subtype, account_type) bucket can legitimately contain more
    than one *distinct* real account (e.g. two people's chequing accounts at the same
    institution, or two credit cards of the same product) — each independently duplicated by
    the re-link. So when a bucket has two or more distinct known mask values, it is partitioned
    by mask first: each mask value's rows form their own duplicate group — this is what an exact
    mask match resolves to, mirroring the preference in canonicalize_account_keys. Rows with no
    mask (pre-mask-column rows) can't be assigned to a specific mask partition by metadata alone;
    if the bucket has more than one known mask, those unmasked rows are logged for manual review
    rather than guessed at.
    """
    by_persistent_id: dict[str, list[dict]] = defaultdict(list)
    by_heuristic: dict[tuple, list[dict]] = defaultdict(list)
    unmatched: list[dict] = []

    for account in accounts:
        if account["persistent_account_id"]:
            by_persistent_id[account["persistent_account_id"]].append(account)
        elif all(account[field] for field in ("official_name", "account_subtype", "account_type")):
            key = (
                account["official_name"],
                account["account_subtype"],
                account["account_type"],
            )
            by_heuristic[key].append(account)
        else:
            unmatched.append(account)

    groups = [g for g in by_persistent_id.values() if len(g) > 1]
    for candidates in by_heuristic.values():
        if len(candidates) < 2:
            continue
        known_masks = {a["mask"] for a in candidates if a["mask"]}
        if len(known_masks) <= 1:
            groups.append(candidates)
            continue

        unmasked = [a for a in candidates if not a["mask"]]
        if unmasked:
            LOGGER.warning(
                "Bucket has %d distinct masks %s; leaving %d unmasked account(s) for "
                "manual review (can't tell which mask they belong to): %s",
                len(known_masks),
                known_masks,
                len(unmasked),
                [a["account_key"] for a in unmasked],
            )
        for mask in known_masks:
            same_mask = [a for a in candidates if a["mask"] == mask]
            if len(same_mask) > 1:
                groups.append(same_mask)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Perform the merge and rehash (default: dry run)"
    )
    parser.add_argument(
        "--rehash-only",
        action="store_true",
        help=(
            "Skip account grouping/merging and only run rehash_transactions() — use this "
            "when accounts are already clean but transaction_hash values need recomputing "
            "under the current build_transaction_hash formula (e.g. after a hash-formula "
            "fix). Implies --apply; writes are always performed."
        ),
    )
    args = parser.parse_args()

    settings = load_settings()
    database = DatabaseClient(settings.database_url)

    if args.rehash_only:
        LOGGER.info("Rehashing transactions under the current hash formula...")
        rehashed, deleted = database.rehash_transactions()
        LOGGER.info(
            "Rehash complete: %d transaction_hash values updated, %d duplicate transactions removed.",
            rehashed,
            deleted,
        )
        return

    accounts = _fetch_accounts(settings.database_url)
    groups = _group_duplicates(accounts)

    if not groups:
        LOGGER.info("No duplicate accounts found.")
        return

    total_moved = 0
    total_dropped = 0
    for group in groups:
        # Canonical = the account_key Plaid is still syncing, not the oldest: upsert_plaid_accounts
        # bumps updated_at on every conflict (db.py), so an orphaned key Plaid no longer issues stays
        # frozen while the live key keeps advancing. Keeping a dead key as canonical would just get
        # re-forked on the next pipeline run, since the incoming account would no longer match it.
        group_sorted = sorted(
            group,
            key=lambda a: (a["updated_at"], a["mask"] is not None, a["created_at"]),
            reverse=True,
        )
        canonical = group_sorted[0]
        duplicates = group_sorted[1:]
        LOGGER.info(
            "Group: canonical=%s (updated %s); duplicates=%s",
            canonical["account_key"],
            canonical["updated_at"],
            [d["account_key"] for d in duplicates],
        )
        for duplicate in duplicates:
            if args.apply:
                moved, dropped = database.merge_account(duplicate["account_key"], canonical["account_key"])
                total_moved += moved
                total_dropped += dropped
                LOGGER.info(
                    "  merged %s -> %s (%d transactions reassigned, %d duplicate rows dropped)",
                    duplicate["account_key"],
                    canonical["account_key"],
                    moved,
                    dropped,
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

    LOGGER.info(
        "Merged %d accounts, %d transactions reassigned, %d duplicate rows dropped. "
        "Rehashing transactions...",
        sum(len(g) - 1 for g in groups),
        total_moved,
        total_dropped,
    )
    rehashed, deleted = database.rehash_transactions()
    LOGGER.info(
        "Rehash complete: %d transaction_hash values updated, %d duplicate transactions removed.",
        rehashed,
        deleted,
    )


if __name__ == "__main__":
    main()
