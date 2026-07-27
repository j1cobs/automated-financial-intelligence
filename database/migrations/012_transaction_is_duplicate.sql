-- User-set "ignore this row as a duplicate" flag. Plaid sometimes returns the same real
-- transaction twice with two transaction_ids and no field that distinguishes the copies from a
-- genuine repeat -- the user really did make four separate IKEA $250.00 charges on 2026-07-02,
-- tapping against a contactless limit, and those are indistinguishable from a double-post.
-- Every attribute matches across the copies; only transaction_id differs.
--
-- No automatic rule can be correct in both directions, so this records the user's judgement.
-- Rows are hidden from analytics, never deleted, so the call is always reversible.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT FALSE;
