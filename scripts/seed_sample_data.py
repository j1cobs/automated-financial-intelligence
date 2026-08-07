#!/usr/bin/env python3
"""Seed curated demo data directly into Postgres — no ingestion, no Plaid credentials.

Sign convention (Plaid): positive amount = outflow (money leaving the account),
negative amount = inflow. This matches app/dashboard.py's `adjusted_amount = -amount`.

This is a deterministic *generator* (random.seed(42)), not a static dump, because the
dashboard only shows the trailing window relative to today — a static dump goes stale
within weeks.

Idempotency: re-running with the same `--days` on the same day is a no-op (identical
amounts/dates -> identical transaction_hash -> ON CONFLICT DO UPDATE rewrites the same
rows). Re-running on a later day shifts the window and inserts the newly covered days.

Usage:
    python scripts/seed_sample_data.py [--days 120]

Reads SEED_DATABASE_URL (not DATABASE_URL) via load_settings() — a dedicated variable so
this script cannot accidentally seed a production database just because DATABASE_URL
happens to point at one. As a second line of defense, it also refuses to write into any
database that already holds non-sample (real) rows unless --force is passed. To undo an
accidental seed, see scripts/purge_sample_data.py.
"""

from __future__ import annotations

import argparse
import logging
import random
from datetime import date, timedelta
from urllib.parse import urlsplit

import pandas as pd

from core.config import load_settings
from database.db import DatabaseClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

SAMPLE_SOURCE = "sample"
SEED = 42

ACCOUNTS = [
    {
        "owner_name": "Alex",
        "account_name": "Alex Chequing",
        "account_type": "depository",
        "account_subtype": "checking",
    },
    {
        "owner_name": "Alex",
        "account_name": "Alex Rewards Visa",
        "account_type": "credit",
        "account_subtype": "credit card",
    },
    {
        "owner_name": "Alex",
        "account_name": "Alex TFSA",
        "account_type": "investment",
        "account_subtype": "tfsa",
    },
    {
        "owner_name": "Sam",
        "account_name": "Sam Chequing",
        "account_type": "depository",
        "account_subtype": "checking",
    },
    {
        "owner_name": "Sam",
        "account_name": "Sam High-Interest Savings",
        "account_type": "depository",
        "account_subtype": "savings",
    },
]

STARTING_BALANCES = {
    "Alex Chequing": 3500.0,
    "Alex Rewards Visa": 0.0,
    "Alex TFSA": 14000.0,
    "Sam Chequing": 4200.0,
    "Sam High-Interest Savings": 9800.0,
}

GROCERY_MERCHANTS = ["Whole Foods Market", "IGA Supermarché", "Provigo"]
DINING_MERCHANTS = ["Tim Hortons", "Starbucks Coffee", "Restaurant St-Denis", "Brasserie locale"]

CHEQUING_BY_OWNER = {"Alex": "Alex Chequing", "Sam": "Sam Chequing"}


def _iter_months(start_date: date, end_date: date):
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _iter_weeks(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=7)


def generate(days: int = 120) -> tuple[list[dict], pd.DataFrame]:
    """Generate deterministic (accounts, transactions_frame) for the trailing `days` window."""
    rng = random.Random(SEED)

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    rows: list[dict] = []

    def add(day: date, description: str, amount: float, account_name: str, category: str) -> None:
        if start_date <= day <= end_date:
            rows.append(
                {
                    "date": day,
                    "description": description,
                    "amount": round(amount, 2),
                    "account_name": account_name,
                    "category": category,
                    "is_outlier": False,
                    "outlier_score": 0.0,
                }
            )

    # Biweekly payroll (1st and 15th)
    for year, month in _iter_months(start_date, end_date):
        for pay_day in (1, 15):
            d = date(year, month, pay_day)
            add(d, "Payroll - Direct Deposit", -2800.0, "Alex Chequing", "Income")
            add(d, "Payroll - Direct Deposit", -2800.0, "Sam Chequing", "Income")

    # Monthly fixed expenses
    for year, month in _iter_months(start_date, end_date):
        add(date(year, month, 1), "Rent", 1350.0, "Alex Chequing", "Housing")
        add(date(year, month, 5), "Hydro - Utility Payment", 85.0, "Sam Chequing", "Utilities")
        add(date(year, month, 12), "Netflix.com", 17.99, "Alex Rewards Visa", "Subscriptions")
        add(date(year, month, 14), "Spotify Premium", 11.99, "Sam Chequing", "Subscriptions")
        add(date(year, month, 2), "STM Opus Card", 100.0, "Sam Chequing", "Transport")

        # Monthly credit-card payment pair (exercises transfer-exclusion logic)
        add(date(year, month, 20), "Payment - Thank You", -350.0, "Alex Rewards Visa", "Transfer")
        add(date(year, month, 20), "Credit Card Payment", 350.0, "Alex Chequing", "Transfer")

        # Biweekly groceries: 2-3x per month per owner
        for _owner, account_name in CHEQUING_BY_OWNER.items():
            for _ in range(rng.randint(2, 3)):
                day_of_month = rng.randint(1, 28)
                add(
                    date(year, month, day_of_month),
                    rng.choice(GROCERY_MERCHANTS),
                    round(rng.uniform(80, 220), 2),
                    account_name,
                    "Groceries",
                )

        # ATM withdrawals: once or twice per month from chequing accounts
        for _owner, account_name in CHEQUING_BY_OWNER.items():
            for _ in range(rng.choice([1, 2])):
                day_of_month = rng.randint(1, 28)
                add(
                    date(year, month, day_of_month),
                    "ATM Withdrawal",
                    float(rng.choice([40, 60, 80, 100, 120])),
                    account_name,
                    "ATM",
                )

    # Weekly restaurant/coffee: 1-2x per week per owner
    for week_start in _iter_weeks(start_date, end_date):
        for _owner, account_name in CHEQUING_BY_OWNER.items():
            for _ in range(rng.choice([1, 2])):
                offset = rng.randint(0, 6)
                add(
                    week_start + timedelta(days=offset),
                    rng.choice(DINING_MERCHANTS),
                    round(rng.uniform(12, 65), 2),
                    account_name,
                    "Dining",
                )

    # Weekly Uber: 1x per week for Alex, from Alex Rewards Visa
    for week_start in _iter_weeks(start_date, end_date):
        offset = rng.randint(0, 6)
        add(
            week_start + timedelta(days=offset),
            "Uber",
            round(rng.uniform(8, 35), 2),
            "Alex Rewards Visa",
            "Transport",
        )

    # 3 anomaly purchases spread across the window, on Alex Rewards Visa
    anomaly_span = max(days - 1, 1)
    anomalies = [
        (rng.randint(0, anomaly_span), "Electronics Store", 450.0, "Shopping"),
        (rng.randint(0, anomaly_span), "Travel Agency", 890.0, "Travel"),
        (rng.randint(0, anomaly_span), "Appliance Purchase", 1200.0, "Shopping"),
    ]
    for offset, description, amount, category in anomalies:
        d = start_date + timedelta(days=offset)
        if start_date <= d <= end_date:
            rows.append(
                {
                    "date": d,
                    "description": description,
                    "amount": amount,
                    "account_name": "Alex Rewards Visa",
                    "category": category,
                    "is_outlier": True,
                    "outlier_score": 0.9,
                }
            )

    frame = pd.DataFrame(rows).sort_values("date", kind="stable").reset_index(drop=True)
    frame["source"] = "sample"
    frame["transaction_id"] = [f"SAMPLE-{i:05d}" for i in range(len(frame))]

    # Running balance per account, in chronological order.
    balances = dict(STARTING_BALANCES)
    computed_balance = []
    for _, row in frame.iterrows():
        account_name = row["account_name"]
        if account_name == "Alex Rewards Visa":
            balances[account_name] += row["amount"]
        else:
            balances[account_name] -= row["amount"]
        computed_balance.append(round(balances[account_name], 2))
    frame["balance"] = computed_balance

    accounts = []
    for account in ACCOUNTS:
        account_name = account["account_name"]
        accounts.append(
            {
                "account_key": f"sample:{account_name}",
                "account_name": account_name,
                "owner_name": account["owner_name"],
                "official_name": account_name,
                "account_type": account["account_type"],
                "account_subtype": account["account_subtype"],
                "balance_available": None,
                "balance_current": balances[account_name],
                "balance_limit": None,
                "iso_currency_code": "CAD",
                "source": "sample",
            }
        )

    return accounts, frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if the target database already holds non-sample (real) rows.",
    )
    args = parser.parse_args()

    settings = load_settings()
    if not settings.seed_database_url:
        LOGGER.error(
            "SEED_DATABASE_URL is not set. This script deliberately does not fall back to "
            "DATABASE_URL, so an accidental seed can never land in a production database. "
            "Set SEED_DATABASE_URL to a disposable/local database and re-run."
        )
        return 1

    db = DatabaseClient(settings.seed_database_url)
    db.ensure_schema()

    counts = db.count_by_source()
    real_accounts = sum(c["accounts"] for s, c in counts.items() if s != SAMPLE_SOURCE)
    real_transactions = sum(c["transactions"] for s, c in counts.items() if s != SAMPLE_SOURCE)
    host = urlsplit(settings.seed_database_url).hostname
    if (real_accounts or real_transactions) and not args.force:
        LOGGER.error(
            "Refusing to seed %s: it already holds %d transactions across %d non-sample "
            "accounts. This looks like a live database. Pass --force only if you are certain.",
            host,
            real_transactions,
            real_accounts,
        )
        return 1

    accounts, frame = generate(days=args.days)
    db.upsert_plaid_accounts(accounts)
    db.upsert_categories(frame["category"].dropna().unique().tolist())
    inserted, updated = db.upsert_transactions(frame)

    LOGGER.info(
        "Seeded %s: %d accounts and %d transactions (%d new, %d already present).",
        host,
        len(accounts),
        len(frame),
        inserted,
        updated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
