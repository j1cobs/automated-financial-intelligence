-- Phase 28: per-month budget caps.
--
-- `budgets` (migration 002) is one row per category with a single monthly_limit
-- and no month dimension, so "budget for October" is inexpressible. This table
-- adds the period, keyed UNIQUE (category, period), and stores only the months
-- a cap was *explicitly* set in -- every other month inherits the most recent
-- earlier cap. See analytics/budget_periods.py::resolve_caps.
--
-- `budgets` itself is deliberately left in place and is NOT read or written by
-- the new path. The frozen Streamlit dashboard both reads it
-- (app/dashboard.py:1116) and writes it (app/dashboard.py:1186, "Save
-- budgets"); mirroring resolved caps back into it would silently discard any
-- budget saved from Streamlit on the next pipeline run.
CREATE TABLE IF NOT EXISTS budget_periods (
    id             BIGSERIAL PRIMARY KEY,
    category       TEXT NOT NULL,
    period         CHAR(7) NOT NULL,          -- 'YYYY-MM'
    monthly_limit  NUMERIC(12, 2) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (category, period)
);

CREATE INDEX IF NOT EXISTS idx_budget_periods_period ON budget_periods(period);

-- One-time seed from the legacy flat table, GUARDED ON AN EMPTY TABLE.
--
-- ensure_schema() re-runs every .sql file on every call, so an unguarded seed
-- would resurrect a cap the user had deliberately cleared: they delete the
-- August row, the next pipeline run re-inserts it. The NOT EXISTS clause is
-- evaluated against the statement-start snapshot, so either every legacy row
-- seeds (first run, empty table) or none do (every run after that).
--
-- Each legacy cap lands at the earliest month present in `transactions`, and
-- carry-forward inheritance covers every month after it -- so one row per
-- category reproduces the old "this limit applies always" behaviour exactly.
INSERT INTO budget_periods (category, period, monthly_limit)
SELECT
    b.category,
    COALESCE(
        (SELECT to_char(MIN(t.date), 'YYYY-MM') FROM transactions t),
        to_char(NOW(), 'YYYY-MM')
    ),
    b.monthly_limit
FROM budgets b
WHERE NOT EXISTS (SELECT 1 FROM budget_periods)
ON CONFLICT (category, period) DO NOTHING;
