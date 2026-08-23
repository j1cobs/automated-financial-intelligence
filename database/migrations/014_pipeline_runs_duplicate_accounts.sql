-- Count of Plaid accounts skipped during ingestion because a co-owned account was
-- already claimed by an earlier token in the same run. Replaces a per-skip log line
-- (which leaked account_id detail into the GitHub Actions log) with a single count
-- recorded alongside the rest of the run's private history.
ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS duplicate_accounts_skipped INTEGER;
