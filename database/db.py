from __future__ import annotations

import datetime as dt
import hashlib
import logging
import pathlib
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import pandas as pd
import psycopg

LOGGER = logging.getLogger(__name__)

_AMOUNT_QUANTUM = Decimal("0.01")  # matches transactions.amount NUMERIC(12, 2)


def _canonical_amount(value: Any) -> str:
    """Render an amount as a fixed 2-dp string regardless of input type.

    float 100.0, Decimal("100.00"), int 100 and "100" must all produce "100.00" —
    the hash must not change depending on whether a row came from the ingestor
    (float) or was read back from the NUMERIC column (Decimal).
    """
    if value is None:
        return ""
    try:
        quantized = Decimal(str(value)).quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return str(value)
    if quantized == 0:
        quantized = abs(quantized)  # collapse Decimal("-0.00") onto "0.00"
    return f"{quantized:.2f}"


def _canonical_date(value: Any) -> str:
    """Render a date as YYYY-MM-DD regardless of date / datetime / Timestamp / str input."""
    if value is None:
        return ""
    if isinstance(value, dt.datetime):  # covers pd.Timestamp (a datetime subclass)
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)[:10]  # ISO-ish strings: "2026-07-01 00:00:00" -> "2026-07-01"


def build_transaction_hash(transaction: dict[str, Any]) -> str:
    identity = "|".join(
        [
            str(transaction.get("account_key", "")),
            _canonical_date(transaction.get("date", "")),
            str(transaction.get("description", "")),
            _canonical_amount(transaction.get("amount", "")),
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
            account_type, account_subtype, persistent_account_id, mask,
            balance_available, balance_current, balance_limit, iso_currency_code,
            source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (account_key) DO UPDATE
        SET account_name          = EXCLUDED.account_name,
            owner_name            = EXCLUDED.owner_name,
            official_name         = EXCLUDED.official_name,
            account_type          = EXCLUDED.account_type,
            account_subtype       = EXCLUDED.account_subtype,
            persistent_account_id = EXCLUDED.persistent_account_id,
            mask                  = EXCLUDED.mask,
            balance_available     = EXCLUDED.balance_available,
            balance_current       = EXCLUDED.balance_current,
            balance_limit         = EXCLUDED.balance_limit,
            iso_currency_code     = EXCLUDED.iso_currency_code,
            source                = EXCLUDED.source,
            updated_at            = NOW()
        """
        rows = [
            (
                a["account_key"],
                a["account_name"],
                a.get("owner_name"),
                a.get("official_name"),
                a.get("account_type"),
                a.get("account_subtype"),
                a.get("persistent_account_id"),
                a.get("mask"),
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

    def canonicalize_account_keys(self, accounts: list[dict[str, Any]]) -> dict[str, str]:
        """Map each incoming account's raw account_key to an existing account_key already
        in the DB that represents the same physical account, so a Plaid Item re-link (which
        issues new account_ids) merges into history instead of creating a duplicate account.

        Matches on `persistent_account_id` first (Plaid's stable cross-relink identifier).
        Falls back to an exact match on official_name + account_subtype + account_type +
        owner_name when `persistent_account_id` is unavailable (e.g. the existing row predates
        that column, or the institution doesn't support it) and the match is unambiguous.
        `mask` is intentionally NOT a required field in that fallback: rows inserted before
        the `mask` column existed have it as NULL, and NULL never equals another value in SQL,
        so requiring it would silently block exactly the historical matches this exists for.
        When `mask` is known on both sides, it is still used to veto a false match.
        """
        remap: dict[str, str] = {}
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                for a in accounts:
                    raw_key = a["account_key"]
                    canonical = None

                    persistent_id = a.get("persistent_account_id")
                    if persistent_id:
                        cur.execute(
                            "SELECT account_key FROM accounts "
                            "WHERE persistent_account_id = %s AND account_key != %s",
                            (persistent_id, raw_key),
                        )
                        row = cur.fetchone()
                        if row:
                            canonical = row[0]

                    if canonical is None:
                        official_name = a.get("official_name")
                        subtype = a.get("account_subtype")
                        account_type = a.get("account_type")
                        owner_name = a.get("owner_name")
                        if official_name and subtype and account_type and owner_name:
                            cur.execute(
                                "SELECT account_key, mask FROM accounts "
                                "WHERE official_name = %s AND account_subtype = %s "
                                "AND account_type = %s AND owner_name = %s AND account_key != %s",
                                (official_name, subtype, account_type, owner_name, raw_key),
                            )
                            new_mask = a.get("mask")
                            matches = [
                                key
                                for key, existing_mask in cur.fetchall()
                                if not (new_mask and existing_mask and new_mask != existing_mask)
                            ]
                            if len(matches) == 1:
                                canonical = matches[0]

                    remap[raw_key] = canonical or raw_key
        return remap

    def merge_account(self, duplicate_key: str, canonical_key: str) -> int:
        """Reassign transactions from duplicate_key onto canonical_key and delete the
        duplicate accounts row. Returns the number of transactions reassigned."""
        if duplicate_key == canonical_key:
            return 0
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE transactions SET account_key = %s, updated_at = NOW() "
                    "WHERE account_key = %s",
                    (canonical_key, duplicate_key),
                )
                moved = cur.rowcount
                cur.execute("DELETE FROM accounts WHERE account_key = %s", (duplicate_key,))
            conn.commit()
        return moved

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

    def update_transaction_recurring(self, transaction_hash: str, is_recurring: bool) -> None:
        """Set is_recurring for a transaction (survives pipeline re-runs)."""
        sql = "UPDATE transactions SET is_recurring = %s, updated_at = NOW() WHERE transaction_hash = %s"
        self._execute_many(sql, [(is_recurring, transaction_hash)])

    def rehash_transactions(self) -> tuple[int, int]:
        """Recompute transaction_hash for every row using the current build_transaction_hash
        formula (account_key-based, with type-canonicalized amount/date). Needed once after
        merge_account calls, since rows inserted before this fix hashed on the fragile
        account_name field. Also needed after the amount/date canonicalization fix (2026-07-19):
        build_transaction_hash previously stringified amount/date with a bare str(), so the
        same transaction hashed differently depending on whether it came from the pipeline
        (float amount, e.g. "100.0") or was read back from Postgres (Decimal amount from the
        NUMERIC column, e.g. "100.00") — every pipeline run after a rehash therefore inserted a
        fresh duplicate instead of updating the existing row. This is the second sanctioned
        change to the hash formula (see Phase 2.7 in PLAN.md for the first); per that amendment,
        any future change to the hash inputs must ship together with a recompute-and-dedupe
        method like this one, never a silent formula swap. Two existing rows that turn out to
        collide under the new formula (the same real transaction, inserted twice under
        different account_keys or different amount/date representations) are deduplicated:
        whichever row already carries the correct new-formula hash survives (falling back to
        the lowest id if neither does), so it needs no UPDATE.

        Two passes are required: the UNIQUE constraint on transaction_hash is enforced against
        the live table, not an in-memory "seen" set, so a single ORDER BY id pass can try to
        UPDATE an earlier row onto a hash that a later row already holds, raising a
        UniqueViolation depending on id order. Deleting every non-keeper duplicate first, then
        updating only the surviving keepers, avoids that collision regardless of id order.

        Returns (rows_rehashed, rows_deleted_as_duplicates).
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, account_key, transaction_date, description, amount, "
                    "transaction_hash FROM transactions ORDER BY id"
                )
                rows = cur.fetchall()

            target_hash_by_id: dict[int, str] = {}
            keeper_by_hash: dict[str, int] = {}
            old_hash_by_id: dict[int, str] = {}
            for row_id, account_key, tx_date, description, amount, old_hash in rows:
                new_hash = build_transaction_hash(
                    {
                        "account_key": account_key,
                        "date": tx_date,
                        "description": description,
                        "amount": amount,
                    }
                )
                target_hash_by_id[row_id] = new_hash
                old_hash_by_id[row_id] = old_hash
                current_keeper = keeper_by_hash.get(new_hash)
                if current_keeper is None or old_hash == new_hash:
                    keeper_by_hash[new_hash] = row_id

            deleted = 0
            rehashed = 0
            with conn.cursor() as cur:
                for row_id, new_hash in target_hash_by_id.items():
                    if keeper_by_hash[new_hash] != row_id:
                        cur.execute("DELETE FROM transactions WHERE id = %s", (row_id,))
                        deleted += 1
                for row_id, new_hash in target_hash_by_id.items():
                    if keeper_by_hash[new_hash] == row_id and new_hash != old_hash_by_id[row_id]:
                        cur.execute(
                            "UPDATE transactions SET transaction_hash = %s WHERE id = %s",
                            (new_hash, row_id),
                        )
                        rehashed += 1
            conn.commit()
        return rehashed, deleted

    def upsert_categories(self, categories: Iterable[str]) -> None:
        sql = """
        INSERT INTO categories (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """
        rows = [(category,) for category in sorted(set(categories)) if category]
        if rows:
            self._execute_many(sql, rows)

    def upsert_transactions(self, frame: pd.DataFrame) -> tuple[int, int]:
        """Insert or refresh transactions. Returns (inserted, updated) counts, where
        "updated" means a transaction_hash that already existed in the table before this
        call (a category/outlier refresh), not a newly-persisted transaction."""
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
        seen_hashes: set[str] = set()
        for record in frame.to_dict("records"):
            transaction_hash = build_transaction_hash(record)
            if transaction_hash in seen_hashes:
                continue
            seen_hashes.add(transaction_hash)
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

        if not rows:
            return 0, 0

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT transaction_hash FROM transactions WHERE transaction_hash = ANY(%s)",
                    (list(seen_hashes),),
                )
                existing_hashes = {row[0] for row in cursor.fetchall()}
                cursor.executemany(sql, rows)
            connection.commit()

        updated = len(existing_hashes)
        inserted = len(rows) - updated
        LOGGER.info(
            "Upserted %s transactions (%s new, %s already present)",
            len(rows), inserted, updated,
        )
        return inserted, updated
