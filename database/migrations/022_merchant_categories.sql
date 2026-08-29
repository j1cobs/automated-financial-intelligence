-- Merchant memory (Phase 18): a user correction on one transaction is remembered here, keyed
-- by a normalized merchant_key (see analytics/categorizer.py), so the cascade can apply it to
-- every future transaction from the same merchant without re-asking the user.
CREATE TABLE IF NOT EXISTS merchant_categories (
    merchant_key TEXT PRIMARY KEY,
    category     TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'user',
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
