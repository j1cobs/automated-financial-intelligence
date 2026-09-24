-- Phase 34: explainable anomalies, replacing the unwired Isolation Forest.
--
-- The existing `transactions.outlier_score` / `is_outlier` columns (migration
-- 001) are per-transaction, but these anomalies are per-category-per-month
-- (drift) or per-stream (price creep) -- a category overspending is not a
-- property of any one transaction. Hence a table of their own.
--
-- `UNIQUE (kind, subject, period)` is what makes detection idempotent across
-- pipeline runs, the same discipline `transaction_hash` provides for
-- transactions. Re-detection updates severity and explanation in place while
-- preserving `detected_at`, so the alert stays current as the month develops
-- but still shows when it first tripped.
CREATE TABLE IF NOT EXISTS anomalies (
    id           BIGSERIAL PRIMARY KEY,
    kind         TEXT NOT NULL,        -- category_drift | price_creep
    subject      TEXT NOT NULL,        -- category name, or stream_id
    period       CHAR(7) NOT NULL,     -- 'YYYY-MM'
    severity     TEXT NOT NULL,        -- medium | high
    explanation  TEXT NOT NULL,        -- generated at detection time, human-readable
    detected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kind, subject, period)
);

CREATE INDEX IF NOT EXISTS idx_anomalies_period ON anomalies(period);

-- Dismissals are PERIOD-SCOPED on purpose. Dismissing September's Dining drift
-- because of a birthday must not silence October's: an alert that never comes
-- back goes quiet exactly as it becomes useful. A category dismissed twelve
-- months running is itself telling the user their cap is wrong.
CREATE TABLE IF NOT EXISTS anomaly_feedback (
    kind         TEXT NOT NULL,
    subject      TEXT NOT NULL,
    period       CHAR(7) NOT NULL,
    dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (kind, subject, period)
);
