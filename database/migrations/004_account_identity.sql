-- Durable account identity, independent of Plaid's per-Item account_id (which changes
-- whenever an Item is re-linked, e.g. after credential rotation).
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS persistent_account_id TEXT;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS mask TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_persistent_id
    ON accounts (persistent_account_id) WHERE persistent_account_id IS NOT NULL;
