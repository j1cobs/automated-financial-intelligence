"""Frame loader: the two raw reads (transactions, accounts) every dashboard path builds on."""

from __future__ import annotations

import pandas as pd
import psycopg


def load_financial_data(database_url: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    tx_query = """
    SELECT
        t.transaction_date   AS date,
        t.transaction_hash,
        t.account_key,
        a.account_name,
        a.owner_name,
        a.account_type,
        a.account_subtype,
        t.description,
        t.amount::double precision AS amount,
        COALESCE(t.user_category, t.category) AS category,
        t.outlier_score,
        t.is_outlier,
        t.is_recurring,
        t.is_duplicate
    FROM transactions t
    JOIN accounts a ON t.account_key = a.account_key
    ORDER BY t.transaction_date DESC
    """
    acct_query = """
    SELECT
        account_key,
        account_name,
        official_name,
        mask,
        owner_name,
        account_type,
        account_subtype,
        COALESCE(balance_available, 0)::double precision AS balance_available,
        COALESCE(balance_current,  0)::double precision AS balance_current,
        balance_limit::double precision AS balance_limit,
        manual_credit_limit::double precision AS manual_credit_limit,
        iso_currency_code,
        updated_at
    FROM accounts
    """
    with psycopg.connect(database_url) as conn:
        tx_df = pd.read_sql(tx_query, conn)
        acct_df = pd.read_sql(acct_query, conn)
    return tx_df, acct_df
