from __future__ import annotations

import hashlib
import logging
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
        migration_path = "database/migrations/001_core_tables.sql"
        with open(migration_path, "r", encoding="utf-8") as migration:
            sql = migration.read()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
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

    def upsert_accounts(self, frame: pd.DataFrame) -> None:
        sql = """
        INSERT INTO accounts (account_key, account_name, source)
        VALUES (%s, %s, %s)
        ON CONFLICT (account_key) DO UPDATE
        SET account_name = EXCLUDED.account_name,
            source = EXCLUDED.source,
            updated_at = NOW()
        """
        rows = []
        for record in frame[["account_name", "source"]].drop_duplicates().to_dict("records"):
            account_name = str(record["account_name"])
            source = str(record["source"])
            rows.append((f"{source}:{account_name}", account_name, source))
        if rows:
            self._execute_many(sql, rows)

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
