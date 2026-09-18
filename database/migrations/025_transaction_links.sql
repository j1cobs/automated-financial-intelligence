-- Link transactions symmetrically (e.g. an expense with its insurance reimbursement),
-- so the dashboard can later net them into one true-cost figure. Survives pipeline
-- re-runs (upsert_transactions never touches this column, same as user_category /
-- is_recurring / is_duplicate). Reversible via unlink_transaction.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS linked_transaction_hash TEXT REFERENCES transactions(transaction_hash);
CREATE INDEX IF NOT EXISTS idx_transactions_linked_transaction_hash ON transactions(linked_transaction_hash);
