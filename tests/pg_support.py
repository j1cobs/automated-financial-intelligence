"""Shared harness for the tests that need a *real* Postgres.

Every other test in this repo mocks `psycopg`, which is why migration 026 shipped
reading `t.date` (the DataFrame alias that `load_financial_data` produces) instead of the
real column `transaction_date`: 614 green tests, and `ensure_schema()` raising
`UndefinedColumn` on the first startup against an actual server. SQL that is only
ever handed to a mock is SQL nobody has checked.

These tests therefore run the real thing, and are **skipped with a stated reason**
when `MIGRATION_TEST_DATABASE_URL` is unset, so the default
`python -m unittest discover -s tests` is unchanged for anyone without a database.

Two safety rules, mirroring the discipline `scripts/seed_sample_data.py` already
applies to `SEED_DATABASE_URL`:

  - **Never `DATABASE_URL`.** Pointing this at the live database would drop a
    schema in it. If the two URLs match, the harness raises rather than skips --
    a silent skip would hide the misconfiguration.
  - **Never `public`.** All work happens in a dedicated `migration_check` schema
    selected through `search_path`. Every migration is unqualified, so everything
    lands there and `public` is untouched even if the URL does point somewhere
    real.
"""

from __future__ import annotations

import os
import pathlib
import unittest
from urllib.parse import quote

import psycopg

#: Everything is created here, never in `public`.
TEST_SCHEMA = "migration_check"

ENV_VAR = "MIGRATION_TEST_DATABASE_URL"

SKIP_REASON = (
    f"set {ENV_VAR} to a scratch Postgres to run the DB-backed suite "
    "(see docs/setup-database.md; CI sets it from a service container)"
)


def scratch_database_url() -> str | None:
    """The scratch URL, or None when the suite should skip.

    Raises rather than returning None when it collides with `DATABASE_URL`: that
    is a misconfiguration to shout about, not a reason to quietly do nothing.
    """
    url = os.environ.get(ENV_VAR)
    if not url:
        return None
    live = os.environ.get("DATABASE_URL")
    if live and url.strip() == live.strip():
        raise RuntimeError(
            f"{ENV_VAR} must not be DATABASE_URL: this suite drops and recreates "
            f"the '{TEST_SCHEMA}' schema. Point it at a scratch database."
        )
    return url


def schema_scoped_url(url: str) -> str:
    """`url` with `search_path` pinned to the test schema.

    The migrations name no schema, so this is what keeps them out of `public`.
    """
    option = quote(f"-csearch_path={TEST_SCHEMA}", safe="")
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}options={option}"


def reset_schema(url: str) -> None:
    """Drop and recreate the test schema. Called per-test for isolation."""
    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE")
            cur.execute(f"CREATE SCHEMA {TEST_SCHEMA}")


def table_names(url: str) -> set[str]:
    with psycopg.connect(schema_scoped_url(url)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
                (TEST_SCHEMA,),
            )
            return {row[0] for row in cur.fetchall()}


class PostgresBackedTestCase(unittest.TestCase):
    """Base: a clean `migration_check` schema per test, with the schema applied.

    Subclasses get `self.url` (schema-scoped, hand this to `DatabaseClient`) and
    `self.admin_url` (the raw URL, for schema maintenance).
    """

    #: Subclasses that want to run the migrations themselves set this False.
    migrate_in_setup = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.admin_url = scratch_database_url()
        if not cls.admin_url:
            raise unittest.SkipTest(SKIP_REASON)
        # `ensure_schema()` globs the relative path "database/migrations", so the
        # suite only works from the repo root. `unittest discover` already does.
        if not pathlib.Path("database/migrations").is_dir():
            raise unittest.SkipTest("run from the repo root: database/migrations not found")
        cls.url = schema_scoped_url(cls.admin_url)

    def setUp(self) -> None:
        super().setUp()
        reset_schema(self.admin_url)
        if self.migrate_in_setup:
            self.client().ensure_schema()

    def client(self):
        from database.db import DatabaseClient

        return DatabaseClient(self.url)

    def execute(self, sql: str, params: tuple | None = None) -> list[tuple]:
        """Run a statement in the test schema and return any rows."""
        with psycopg.connect(self.url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if cur.description else []
            conn.commit()
        return rows

    def seed_account(self, account_key: str = "test:checking") -> str:
        self.execute(
            "INSERT INTO accounts (account_key, account_name, account_type, "
            "balance_current, source) VALUES (%s, %s, %s, %s, %s)",
            (account_key, "Test Chequing", "depository", 5000.00, "test"),
        )
        return account_key

    def seed_transaction(
        self,
        transaction_hash: str,
        transaction_date: str,
        description: str,
        amount: float,
        account_key: str = "test:checking",
        merchant_name: str | None = None,
    ) -> str:
        self.execute(
            "INSERT INTO transactions (transaction_hash, account_key, transaction_date, "
            "description, amount, merchant_name) VALUES (%s, %s, %s, %s, %s, %s)",
            (transaction_hash, account_key, transaction_date, description, amount, merchant_name),
        )
        return transaction_hash
