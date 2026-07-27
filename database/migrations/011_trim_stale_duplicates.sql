-- Trim the one class of stored duplicate that is provably safe to remove from SQL alone.
--
-- The co-owned account with mask '4102' is exposed through two different Plaid Items. Each
-- real transaction on it is therefore delivered twice, under two different transaction_ids, so
-- neither transactions_external_id (009) nor the account-scoped transaction_hash suppresses the
-- second copy -- most visibly the recurring `$0.00 Fixed monthly fees`, stored twice.
--
-- Scope is deliberately narrow. Elsewhere in this table an exact repeat of
-- (account_key, transaction_date, description, amount) is frequently REAL spending (four
-- genuine `IKEA $250.00` charges on 2026-07-02 against a contactless limit -- see 010), so this
-- delete must never be widened beyond the double-Item account. The remaining stale duplicates
-- are removed by DatabaseClient.reconcile_transactions() on the next pipeline run, because only
-- that has Plaid's own per-natural-key counts to compare against.
--
-- ensure_schema() re-runs every migration on every call, so this is written to be idempotent:
-- once the later copies are gone it matches nothing and deletes nothing.
DELETE FROM transactions t
USING transactions earlier, accounts a
WHERE t.account_key = a.account_key
  AND a.mask = '4102'
  AND earlier.account_key = t.account_key
  AND earlier.transaction_date = t.transaction_date
  AND earlier.description = t.description
  AND earlier.amount = t.amount
  AND (earlier.created_at, earlier.id) < (t.created_at, t.id);
