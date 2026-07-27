-- Retire stale attributions. When Plaid re-attributes a transaction to a different account_id
-- (institution renumbering, account migration, a corrected mapping), the pipeline appended the new
-- attribution without retiring the old row, because every uniqueness guarantee was account-scoped:
-- transactions_natural_key (005) is keyed on account_key, and so is transaction_hash. Keep the most
-- recently ingested copy: that is Plaid's current attribution.
DELETE FROM transactions t
USING transactions newer
WHERE t.external_id IS NOT NULL
  AND t.external_id = newer.external_id
  AND (t.created_at, t.id) < (newer.created_at, newer.id);

-- Enforce it going forward. external_id is Plaid's globally unique transaction_id and is
-- account-independent, so it catches duplicates that no account-identity heuristic can --
-- including the case that prompted this, where two accounts have legitimately different masks
-- and Plaid moved 60 transactions from one to the other.
CREATE UNIQUE INDEX IF NOT EXISTS transactions_external_id
    ON transactions (external_id) WHERE external_id IS NOT NULL;
