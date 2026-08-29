-- Plaid's `personal_finance_category` and enriched merchant name (Phase 18), plus a marker
-- for which cascade layer set `category` on a given row.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pfc_primary    TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pfc_detailed   TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS pfc_confidence TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS merchant_name  TEXT;

-- category_source records which cascade layer set `category`: 'plaid' (Plaid's PFC primary),
-- 'merchant' (a remembered user correction for this merchant), 'user' (placeholder/legacy —
-- reserved should a future layer need to distinguish a direct per-row correction from a
-- merchant-memory backfill), or 'none' (nothing matched, category is UNCATEGORIZED). This is
-- what makes the cascade debuggable and what a future layer-3 (TF-IDF) decision gets measured
-- against.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_source TEXT;
