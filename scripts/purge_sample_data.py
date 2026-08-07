"""Remove demo data written by scripts/seed_sample_data.py.

Every row the seed script writes is namespaced under `source = "sample"` (accounts) —
`account_key` values like `sample:Alex Chequing`, and transactions whose `external_id`
is `SAMPLE-00000`, etc. Nothing else in the codebase writes that source value, so this
script only ever touches seed-generated rows; real Plaid data (`source = "plaid"`) is
never in scope.

Usage:
    python scripts/purge_sample_data.py            # report only, no writes
    python scripts/purge_sample_data.py --apply    # delete
"""

from __future__ import annotations

import argparse
import logging

from core.config import load_settings
from database.db import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

SAMPLE_SOURCE = "sample"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the deletion (default: dry run)")
    args = parser.parse_args()

    settings = load_settings()
    db = DatabaseClient(settings.database_url)

    sample_accounts = db.accounts_for_source(SAMPLE_SOURCE)
    if not sample_accounts:
        LOGGER.info("No sample data found.")
        return 0

    total_transactions = sum(a["transaction_count"] for a in sample_accounts)
    LOGGER.info("%d sample accounts, %d sample transactions", len(sample_accounts), total_transactions)
    for account in sample_accounts:
        LOGGER.info("  %-30s (%d txns)", account["account_key"], account["transaction_count"])

    counts = db.count_by_source()
    other_accounts = sum(c["accounts"] for s, c in counts.items() if s != SAMPLE_SOURCE)
    other_transactions = sum(c["transactions"] for s, c in counts.items() if s != SAMPLE_SOURCE)

    if not args.apply:
        LOGGER.info(
            "[dry run] would delete %d transactions, %d accounts", total_transactions, len(sample_accounts)
        )
        LOGGER.info(
            "Real (non-sample) rows untouched: %d txns / %d accounts", other_transactions, other_accounts
        )
        LOGGER.info("Re-run with --apply to delete.")
        return 0

    transactions_deleted, accounts_deleted = db.purge_source(SAMPLE_SOURCE)
    LOGGER.info("Deleted %d transactions, %d accounts.", transactions_deleted, accounts_deleted)
    LOGGER.info("Real (non-sample) rows untouched: %d txns / %d accounts", other_transactions, other_accounts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
