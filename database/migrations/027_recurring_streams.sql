-- Phase 30: recurring charges as detected *streams*, not a per-row boolean.
--
-- `transactions.is_recurring` (migration 006) is a bare per-row flag with no
-- series concept, so every occurrence of the same charge is independently
-- checkable and the Overview list groups by raw description and guesses cadence
-- from the median gap between rows. A stream is the thing the user actually
-- means by "recurring": one merchant, one cadence, a predicted next date.
--
-- `stream_id` is Plaid's own id when the stream came from
-- /transactions/recurring/get, or 'local:<merchant_key>' when it was derived
-- from our own history. Both shapes live in this table so everything
-- downstream is indifferent to which path produced the row.
CREATE TABLE IF NOT EXISTS recurring_streams (
    stream_id            TEXT PRIMARY KEY,
    merchant_key         TEXT NOT NULL,
    description          TEXT NOT NULL,
    category             TEXT,
    cadence              TEXT,                 -- WEEKLY | BIWEEKLY | MONTHLY | ANNUALLY | UNKNOWN
    direction            TEXT NOT NULL,        -- inflow | outflow
    last_amount          NUMERIC(12,2),
    last_date            DATE,
    predicted_next_date  DATE,
    status               TEXT,                 -- mature | early_detection
    source               TEXT NOT NULL,        -- plaid | local
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recurring_streams_merchant ON recurring_streams(merchant_key);
CREATE INDEX IF NOT EXISTS idx_recurring_streams_active ON recurring_streams(is_active);
