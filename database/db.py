from __future__ import annotations

import datetime as dt
import hashlib
import logging
import pathlib
from collections import Counter
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
    """Identify a transaction by Plaid's `transaction_id` when there is one, else by
    `account_key|date|description|amount`.

    `transaction_hash` carries a UNIQUE constraint, so whatever this hashes is what the table
    can hold at most one of. That makes an account-scoped formula unusable: it would permit
    only a single row per (account_key, date, description, amount) and so cannot represent
    genuinely repeated transactions. This data contains them — the user made four separate real
    `IKEA $250.00` charges on 2026-07-02, tapping repeatedly against a $250 contactless limit.
    An account-scoped formula was tried and reverted precisely because it silently destroys
    three of those four.

    Hashing the transaction_id also makes the hash stable across Plaid mutating a transaction's
    attributes (the pending -> posted transition revises amount, date and description) and
    across Plaid re-attributing it to a different account_id. Both then collide on the hash and
    UPDATE the existing row in place rather than inserting a twin.

    What this formula does *not* catch is a *re-issued* transaction_id: after an Item re-link
    the same real transaction returns under a brand-new id, hashes differently, and lands as a
    second row. That class is deliberately handled outside the schema, by
    DatabaseClient.reconcile_transactions(), which trims stored copies down to the number Plaid
    itself currently returns per natural key. It is the only mechanism with enough information
    to tell four real IKEA taps from four duplicates.

    Rows with no transaction_id (seed data, future non-Plaid sources) fall back to the
    account-scoped formula, which is the best identity available for them.

    Per the Phase 2.7 amendment in PLAN.md, any change to the hash inputs ships together with
    rehash_transactions(), which recomputes every stored hash and dedupes collisions — never a
    silent formula swap.
    """
    external_id = transaction.get("external_id") or transaction.get("transaction_id")
    if external_id:
        return hashlib.sha256(f"plaid_txn|{external_id}".encode()).hexdigest()
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

    def log_pipeline_run(
        self,
        started_at: dt.datetime,
        status: str,
        *,
        transactions_inserted: int | None = None,
        transactions_updated: int | None = None,
        stale_duplicates_removed: int | None = None,
        duplicate_accounts_skipped: int | None = None,
        error_class: str | None = None,
        error_message: str | None = None,
        trigger_type: str | None = None,
    ) -> None:
        """Record one pipeline run for private, queryable history — this is where per-run detail
        (counts, errors) lives instead of the GitHub Actions log, which is visible to anyone with
        repo read access. `trigger_type` ("schedule" / "workflow_dispatch" / "local") distinguishes
        the daily cron from a manual run, so two same-day rows are self-explanatory rather than
        looking like a duplicate-write bug."""
        sql = """
        INSERT INTO pipeline_runs (
            started_at, status, transactions_inserted, transactions_updated,
            stale_duplicates_removed, duplicate_accounts_skipped, error_class, error_message,
            trigger_type
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        started_at,
                        status,
                        transactions_inserted,
                        transactions_updated,
                        stale_duplicates_removed,
                        duplicate_accounts_skipped,
                        error_class,
                        error_message,
                        trigger_type,
                    ),
                )
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

    def count_by_source(self) -> dict[str, dict[str, int]]:
        """{source: {"accounts": n, "transactions": m}} for every source present in `accounts`."""
        sql = """
        SELECT a.source, COUNT(DISTINCT a.account_key), COUNT(t.id)
        FROM accounts a
        LEFT JOIN transactions t ON t.account_key = a.account_key
        GROUP BY a.source
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return {
            source: {"accounts": accounts, "transactions": transactions}
            for source, accounts, transactions in rows
        }

    def accounts_for_source(self, source: str) -> list[dict[str, Any]]:
        """Per-account breakdown (account_key, account_name, transaction count) for one source."""
        sql = """
        SELECT a.account_key, a.account_name, COUNT(t.id) AS transaction_count
        FROM accounts a
        LEFT JOIN transactions t ON t.account_key = a.account_key
        WHERE a.source = %s
        GROUP BY a.account_key, a.account_name
        ORDER BY a.account_key
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (source,))
                rows = cur.fetchall()
        return [{"account_key": r[0], "account_name": r[1], "transaction_count": r[2]} for r in rows]

    def purge_source(self, source: str) -> tuple[int, int]:
        """Delete every transaction belonging to `source`'s accounts, then the accounts
        themselves. Returns (transactions_deleted, accounts_deleted)."""
        if not source:
            raise ValueError("source must be a non-empty string")
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM transactions
                    WHERE account_key IN (SELECT account_key FROM accounts WHERE source = %s)
                    """,
                    (source,),
                )
                transactions_deleted = cur.rowcount
                cur.execute("DELETE FROM accounts WHERE source = %s", (source,))
                accounts_deleted = cur.rowcount
            conn.commit()
        return transactions_deleted, accounts_deleted

    def canonicalize_account_keys(self, accounts: list[dict[str, Any]]) -> dict[str, str]:
        """Map each incoming account's raw account_key to an existing account_key already
        in the DB that represents the same physical account, so a Plaid Item re-link (which
        issues new account_ids) merges into history instead of creating a duplicate account.

        Matches on `persistent_account_id` first (Plaid's stable cross-relink identifier).
        Falls back to an exact match on official_name + account_subtype + account_type when
        `persistent_account_id` is unavailable (e.g. the existing row predates that column, or
        the institution doesn't support it) and the match is unambiguous. `owner_name` is
        deliberately excluded: it records which connection/token revealed the account, not who
        owns it, so a jointly-held account visible through two different tokens would otherwise
        bucket separately and could never merge.

        `mask` is intentionally NOT a required field in that fallback: rows inserted before
        the `mask` column existed have it as NULL, and NULL never equals another value in SQL,
        so requiring it would silently block exactly the historical matches this exists for.
        When `mask` is known on both sides, it is used to veto a false match, and an exact mask
        match is preferred outright when the fallback would otherwise be ambiguous (e.g. two
        accounts sharing official_name/subtype/type, one with a known mask and one still NULL
        from before this field was backfilled).
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
                        if official_name and subtype and account_type:
                            cur.execute(
                                "SELECT account_key, mask FROM accounts "
                                "WHERE official_name = %s AND account_subtype = %s "
                                "AND account_type = %s AND account_key != %s",
                                (official_name, subtype, account_type, raw_key),
                            )
                            candidates = cur.fetchall()
                            new_mask = a.get("mask")
                            matches = [
                                key
                                for key, existing_mask in candidates
                                if not (new_mask and existing_mask and new_mask != existing_mask)
                            ]
                            if new_mask:
                                exact = [
                                    key for key, existing_mask in candidates if existing_mask == new_mask
                                ]
                                if len(exact) == 1:
                                    canonical = exact[0]
                            if canonical is None and len(matches) == 1:
                                canonical = matches[0]

                    remap[raw_key] = canonical or raw_key
        return remap

    def merge_account(self, duplicate_key: str, canonical_key: str) -> tuple[int, int]:
        """Reassign transactions from duplicate_key onto canonical_key and delete the
        duplicate accounts row. Rows that would collide with an existing canonical row under
        transactions_natural_key (migration 005) are dropped first — the same real transaction
        ingested twice under two account_keys — otherwise the UPDATE raises a unique violation.
        Also carries manual_credit_limit onto the canonical row when the canonical's is NULL, so
        a user-entered credit limit (migration 007) is not lost with the deleted row.
        Returns (transactions_reassigned, duplicates_dropped)."""
        if duplicate_key == canonical_key:
            return 0, 0
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM transactions d
                    WHERE d.account_key = %s
                      AND EXISTS (
                          SELECT 1 FROM transactions c
                          WHERE c.account_key = %s
                            AND c.transaction_date = d.transaction_date
                            AND c.description = d.description
                            AND c.amount = d.amount
                      )
                    """,
                    (duplicate_key, canonical_key),
                )
                dropped = cur.rowcount
                cur.execute(
                    "UPDATE transactions SET account_key = %s, updated_at = NOW() WHERE account_key = %s",
                    (canonical_key, duplicate_key),
                )
                moved = cur.rowcount
                cur.execute(
                    """
                    UPDATE accounts SET manual_credit_limit = (
                        SELECT manual_credit_limit FROM accounts WHERE account_key = %s
                    )
                    WHERE account_key = %s AND manual_credit_limit IS NULL
                    """,
                    (duplicate_key, canonical_key),
                )
                cur.execute("DELETE FROM accounts WHERE account_key = %s", (duplicate_key,))
            conn.commit()
        return moved, dropped

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

    def set_manual_credit_limit(self, account_key: str, limit: float | None) -> None:
        """Set (or clear, with limit=None) the manually-entered credit limit for an
        account. Does not touch updated_at, which is used elsewhere as a Plaid balance
        freshness signal."""
        sql = "UPDATE accounts SET manual_credit_limit = %s WHERE account_key = %s"
        self._execute_many(sql, [(limit, account_key)])

    def update_transaction_category(self, transaction_hash: str, category: str) -> None:
        """Set user_category for a transaction (survives pipeline re-runs).
        Also inserts the category into the categories table so it appears in future dropdowns.
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (category,)
                )
                cur.execute(
                    "UPDATE transactions SET user_category = %s, updated_at = NOW() "
                    "WHERE transaction_hash = %s",
                    (category, transaction_hash),
                )
            conn.commit()

    def update_transaction_recurring(self, transaction_hash: str, is_recurring: bool) -> None:
        """Set is_recurring for a transaction (survives pipeline re-runs)."""
        sql = "UPDATE transactions SET is_recurring = %s, updated_at = NOW() WHERE transaction_hash = %s"
        self._execute_many(sql, [(is_recurring, transaction_hash)])

    def update_transaction_duplicate(self, transaction_hash: str, is_duplicate: bool) -> None:
        """Flag a transaction as a duplicate to hide it from analytics (survives pipeline re-runs).

        Plaid can return the same real transaction twice under two transaction_ids with no field
        distinguishing the copies from a genuine repeat, so this records a judgement only the user
        can make. The row is retained, never deleted, so the flag is always reversible.
        """
        sql = "UPDATE transactions SET is_duplicate = %s, updated_at = NOW() WHERE transaction_hash = %s"
        self._execute_many(sql, [(is_duplicate, transaction_hash)])

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

        A prior pass collapses rows sharing an external_id, keeping the newest copy (Plaid's
        current attribution), which is what the transactions_external_id unique index from
        migration 009 enforces going forward. It survives the hash change because a row can
        hold a stale external_id from before that index existed.

        Returns (rows_rehashed, rows_deleted_as_duplicates).
        """
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM transactions t
                    USING transactions newer
                    WHERE t.external_id IS NOT NULL
                      AND t.external_id = newer.external_id
                      AND (t.created_at, t.id) < (newer.created_at, newer.id)
                    """
                )
                external_id_deleted = cur.rowcount
            conn.commit()

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, account_key, transaction_date, description, amount, "
                    "transaction_hash, external_id FROM transactions ORDER BY id"
                )
                rows = cur.fetchall()

            target_hash_by_id: dict[int, str] = {}
            keeper_by_hash: dict[str, int] = {}
            old_hash_by_id: dict[int, str] = {}
            for row_id, account_key, tx_date, description, amount, old_hash, external_id in rows:
                new_hash = build_transaction_hash(
                    {
                        "account_key": account_key,
                        "date": tx_date,
                        "description": description,
                        "amount": amount,
                        "external_id": external_id,
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
        return rehashed, deleted + external_id_deleted

    def upsert_categories(self, categories: Iterable[str]) -> None:
        sql = """
        INSERT INTO categories (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """
        rows = [(category,) for category in sorted(set(categories)) if category]
        if rows:
            self._execute_many(sql, rows)

    def reconcile_transactions(self, frame: pd.DataFrame, start_date, end_date) -> int:
        """Trim stored duplicate transactions using Plaid's own per-natural-key counts.

        Why this exists: persistence is append-only, and the same real transaction can arrive
        again carrying a *new* Plaid transaction_id — after an Item re-link, or when one real
        account is exposed through two different Plaid Items. Neither existing guard catches
        that. transactions_external_id (migration 009) sees two different ids and allows both,
        and the account-scoped transaction_hash only absorbs the copy if it lands on the same
        canonical account_key, which a second Item does not guarantee. The excess copies
        therefore accumulate.

        Why there is no unique index for this: a natural-key index on
        (account_key, transaction_date, description, amount) cannot tell a duplicate from a
        genuinely repeated purchase. The user really did make four separate `IKEA $250.00`
        charges on 2026-07-02, tapping repeatedly against a $250 contactless limit. Migration
        005 added such an index and migration 010 dropped it for exactly this reason; it must
        never be recreated.

        The only reliable discriminator is Plaid itself: for a natural key, how many copies
        does Plaid currently return for this window? Five stored IKEA rows against four
        fetched means exactly one is spurious. Excess rows are deleted newest-first, keeping
        the earliest by (created_at, id) so user_category, is_recurring and the original
        created_at survive.

        A natural key Plaid returns *zero* of is skipped outright and never touched. Plaid's
        transaction window rolls forward and drops old history the database legitimately still
        holds (e.g. `ANTHROPIC* CLAUDE SUB 32.19`). Absence from the fetch is not evidence of
        duplication — this guard is the most important safety property of this method.

        `frame` must already carry canonical account_keys (the caller remaps them via
        canonicalize_account_keys) or stored and fetched rows would bucket separately. Amounts
        and dates are compared through _canonical_amount / _canonical_date on *both* sides:
        the frame carries Python floats and date/Timestamp values while Postgres returns
        Decimal and date, and that exact mismatch has already caused a duplicate-insert bug
        here.

        Returns the number of rows deleted.
        """
        fetched_counts: Counter[tuple[str, str, str, str]] = Counter()
        for record in frame.to_dict("records"):
            fetched_counts[
                (
                    str(record.get("account_key", "")),
                    _canonical_date(record.get("date")),
                    str(record.get("description", "")),
                    _canonical_amount(record.get("amount")),
                )
            ] += 1

        fetched_external_ids = {
            str(record["transaction_id"])
            for record in frame.to_dict("records")
            if record.get("transaction_id")
        }

        doomed_ids: list[int] = []
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, account_key, transaction_date, description, amount, created_at, "
                    "external_id, is_duplicate FROM transactions "
                    "WHERE transaction_date BETWEEN %s AND %s",
                    (start_date, end_date),
                )
                stored_rows = cur.fetchall()

            grouped: dict[tuple[str, str, str, str], list[tuple[bool, bool, Any, int]]] = {}
            for (
                row_id,
                account_key,
                tx_date,
                description,
                amount,
                created_at,
                external_id,
                is_duplicate,
            ) in stored_rows:
                key = (
                    str(account_key or ""),
                    _canonical_date(tx_date),
                    str(description or ""),
                    _canonical_amount(amount),
                )
                is_current = bool(external_id) and str(external_id) in fetched_external_ids
                grouped.setdefault(key, []).append((bool(is_duplicate), is_current, created_at, row_id))

            for key, rows in grouped.items():
                fetched_count = fetched_counts.get(key, 0)
                if fetched_count == 0:
                    # Plaid no longer returns this transaction at all — real history that has
                    # aged out of Plaid's window. Never delete on absence.
                    continue
                excess = len(rows) - fetched_count
                if excess <= 0:
                    continue
                # Deletion order, most-expendable last:
                #   1. Rows the user flagged as duplicates go first — they have already been
                #      judged expendable, so trimming must never remove their unflagged twin
                #      instead and leave the flagged copy behind.
                #   2. Rows whose external_id Plaid still returns are kept ahead of ones it does
                #      not. Sorting purely by created_at would keep the *stale* copy (it is
                #      older) and delete the freshly-ingested current one, so the next run
                #      re-inserts it and the pipeline thrashes forever.
                #   3. Among otherwise-equal rows the earliest wins, so user_category /
                #      is_recurring / created_at survive.
                rows.sort(key=lambda r: (r[0], not r[1], r[2], r[3]))
                doomed_ids.extend(row_id for *_, row_id in rows[fetched_count:])

            if doomed_ids:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM transactions WHERE id = ANY(%s)", (doomed_ids,))
                conn.commit()

        return len(doomed_ids)

    def upsert_transactions(self, frame: pd.DataFrame) -> tuple[int, int]:
        """Insert or refresh transactions. Returns (inserted, updated) counts, where
        "updated" means a transaction_hash that already existed in the table before this
        call (a category/outlier refresh), not a newly-persisted transaction.

        Identity is `transaction_hash`, which build_transaction_hash derives from Plaid's
        `transaction_id` whenever there is one. That makes the hash stable across the two ways
        Plaid mutates a transaction in place: the pending -> posted transition, which revises
        amount / date / description, and re-attribution to a different account_key. Both
        therefore arrive with an unchanged hash and are absorbed by the ON CONFLICT clause,
        which carries account_key / date / description / amount across rather than inserting a
        twin. An earlier account-scoped hash needed a pre-insert relocation pass to achieve the
        same thing; that pass was removed along with the hash change.

        `external_id = EXCLUDED.external_id` is in the conflict clause so a re-issued
        transaction_id follows its row instead of being rejected later by the
        transactions_external_id unique index (migration 009).

        What this does NOT handle is a transaction returning under a genuinely *new*
        transaction_id after an Item re-link: that hashes differently and lands as a second
        row. reconcile_transactions() trims those against the count Plaid itself reports.

        Columns the user owns — user_category, is_recurring, is_duplicate — are deliberately
        absent from both the INSERT list and the conflict-update list, so a pipeline run can
        never clear a manual edit. Keep them out when adding columns here.
        """
        # No relocation pass is needed: build_transaction_hash keys on the transaction_id, so a
        # transaction Plaid has revised (pending -> posted) or re-attributed to another account
        # arrives with an unchanged hash and is absorbed by the ON CONFLICT clause below, which
        # carries account_key / date / description / amount across. An earlier account-scoped
        # hash did need such a pass; it was removed with the hash change.
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
        SET external_id = EXCLUDED.external_id,
            account_key = EXCLUDED.account_key,
            transaction_date = EXCLUDED.transaction_date,
            description = EXCLUDED.description,
            amount = EXCLUDED.amount,
            category = EXCLUDED.category,
            outlier_score = EXCLUDED.outlier_score,
            is_outlier = EXCLUDED.is_outlier,
            updated_at = NOW()
        """
        rows = []
        seen_hashes: set[str] = set()
        for record in frame.to_dict("records"):
            transaction_hash = build_transaction_hash(record)
            # The account-scoped hash also covers the repeated-transaction_id case (unstable
            # pagination repeating a row across pages), so no separate external_id guard is
            # needed: the same Plaid row twice in one batch has the same hash twice.
            if transaction_hash in seen_hashes:
                continue
            external_id = record.get("transaction_id") or None
            seen_hashes.add(transaction_hash)
            account_key = (
                record.get("account_key")
                or f"{record.get('source', 'unknown')}:{record.get('account_name', 'unknown')}"
            )
            rows.append(
                (
                    external_id,
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
        return inserted, updated
