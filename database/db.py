from __future__ import annotations

import hashlib
import logging
import pathlib
from collections.abc import Iterable
from typing import Any

import pandas as pd
import psycopg

LOGGER = logging.getLogger(__name__)


def build_transaction_hash(transaction: dict[str, Any]) -> str:
    identity = "|".join(
        [
            str(transaction.get("account_name", "")),
            str(transaction.get("date", "")),
            str(transaction.get("description", "")),
            str(transaction.get("amount", "")),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


class DatabaseClient:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def _execute_many(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(sql, rows)
            connection.commit()

    def ensure_schema(self) -> None:
        migrations_dir = pathlib.Path("database/migrations")
        sql_files = sorted(migrations_dir.glob("*.sql"))
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for sql_file in sql_files:
                    cursor.execute(sql_file.read_text(encoding="utf-8"))
            connection.commit()

    def upsert_plaid_accounts(self, accounts: list[dict[str, Any]]) -> None:
        sql = """
        INSERT INTO accounts (
            account_key, account_name, owner_name, official_name,
            account_type, account_subtype,
            balance_available, balance_current, balance_limit, iso_currency_code,
            source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (account_key) DO UPDATE
        SET account_name      = EXCLUDED.account_name,
            owner_name        = EXCLUDED.owner_name,
            official_name     = EXCLUDED.official_name,
            account_type      = EXCLUDED.account_type,
            account_subtype   = EXCLUDED.account_subtype,
            balance_available = EXCLUDED.balance_available,
            balance_current   = EXCLUDED.balance_current,
            balance_limit     = EXCLUDED.balance_limit,
            iso_currency_code = EXCLUDED.iso_currency_code,
            source            = EXCLUDED.source,
            updated_at        = NOW()
        """
        rows = [
            (
                a["account_key"],
                a["account_name"],
                a.get("owner_name"),
                a.get("official_name"),
                a.get("account_type"),
                a.get("account_subtype"),
                a.get("balance_available"),
                a.get("balance_current"),
                a.get("balance_limit"),
                a.get("iso_currency_code"),
                a["source"],
            )
            for a in accounts
        ]
        if rows:
            self._execute_many(sql, rows)

    def get_categories(self) -> list[str]:
        """Return all category names from the categories table, sorted."""
        sql = "SELECT name FROM categories ORDER BY name"
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [r[0] for r in rows]

    def get_budgets(self) -> list[dict]:
        """Return all budget rows as a list of dicts: {category, monthly_limit}."""
        sql = "SELECT category, monthly_limit::double precision FROM budgets ORDER BY category"
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [{"category": r[0], "monthly_limit": r[1]} for r in rows]

    def upsert_budget(self, category: str, monthly_limit: float) -> None:
        """Insert or update a budget row."""
        sql = """
        INSERT INTO budgets (category, monthly_limit)
        VALUES (%s, %s)
        ON CONFLICT (category) DO UPDATE
        SET monthly_limit = EXCLUDED.monthly_limit,
            updated_at    = NOW()
        """
        self._execute_many(sql, [(category, monthly_limit)])

    def update_transaction_category(self, transaction_hash: str, category: str) -> None:
        """Set user_category for a transaction (survives pipeline re-runs).
        Also inserts the category into the categories table so it appears in future dropdowns.
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                    (category,)
                )
                cur.execute(
                    "UPDATE transactions SET user_category = %s, updated_at = NOW() WHERE transaction_hash = %s",
                    (category, transaction_hash)
                )
            conn.commit()

    def upsert_categories(self, categories: Iterable[str]) -> None:
        sql = """
        INSERT INTO categories (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """
        rows = [(category,) for category in sorted(set(categories)) if category]
        if rows:
            self._execute_many(sql, rows)

    def upsert_transactions(self, frame: pd.DataFrame) -> None:
        sql = """
        INSERT INTO transactions (
            external_id,
            transaction_hash,
            account_key,
            transaction_date,
            description,
            amount,
            balance,
            category,
            outlier_score,
            is_outlier
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (transaction_hash) DO UPDATE
        SET category = EXCLUDED.category,
            outlier_score = EXCLUDED.outlier_score,
            is_outlier = EXCLUDED.is_outlier,
            updated_at = NOW()
        """
        rows = []
        for record in frame.to_dict("records"):
            transaction_hash = build_transaction_hash(record)
            account_key = record.get("account_key") or f"{record.get('source', 'unknown')}:{record.get('account_name', 'unknown')}"
            rows.append(
                (
                    record.get("transaction_id") or None,
                    transaction_hash,
                    account_key,
                    record.get("date"),
                    str(record.get("description", "")),
                    float(record.get("amount", 0.0)),
                    record.get("balance"),
                    record.get("category"),
                    float(record.get("outlier_score", 0.0)),
                    bool(record.get("is_outlier", False)),
                )
            )

        if rows:
            self._execute_many(sql, rows)
            LOGGER.info("Upserted %s transactions", len(rows))
