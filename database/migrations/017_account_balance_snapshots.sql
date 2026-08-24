-- Historical daily balances per account. `accounts.balance_current` is overwritten in place
-- on every pipeline run, so net worth over time was previously impossible to reconstruct from
-- stored data -- this table is what makes that chart buildable. One row per
-- (account_key, snapshot_date); a same-day re-run (the daily schedule plus a manual
-- workflow_dispatch, or a local run, can both legitimately hit the same day) overwrites that
-- day's snapshot rather than creating a second one, since only the latest balance observed
-- that day is meaningful. History starts the day this ships -- there is no way to backfill
-- past balances.
CREATE TABLE IF NOT EXISTS account_balance_snapshots (
    id BIGSERIAL PRIMARY KEY,
    account_key TEXT NOT NULL REFERENCES accounts(account_key),
    snapshot_date DATE NOT NULL,
    balance_current NUMERIC(12,2),
    balance_available NUMERIC(12,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (account_key, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_account_balance_snapshots_date ON account_balance_snapshots(snapshot_date);
