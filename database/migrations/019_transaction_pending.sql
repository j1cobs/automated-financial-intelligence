-- `pending` is nullable on purpose: NULL means "ingested before this phase, status unknown"
-- (the existing pre-sync rows) and must never be treated as, or confused with, FALSE.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pending BOOLEAN;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pending_transaction_id TEXT;
