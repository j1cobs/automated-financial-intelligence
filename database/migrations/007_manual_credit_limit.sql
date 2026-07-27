-- User-entered credit limit, for cards where the institution does not expose
-- balances.limit to Plaid (both balance_limit and balance_available come back NULL,
-- so utilisation cannot be derived arithmetically).
-- Deliberately a separate column from balance_limit: upsert_plaid_accounts overwrites
-- balance_limit on every pipeline run, but does not name this column, so the manual
-- value survives. Plaid's value takes precedence when present.
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS manual_credit_limit NUMERIC(12,2);
