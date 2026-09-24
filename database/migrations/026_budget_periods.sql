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

-- One-time seed from the legacy flat table, GUARDED ON A PERSISTENT MARKER.
--
-- ensure_schema() re-runs every .sql file on every call, so an unguarded seed
-- would resurrect a cap the user had deliberately cleared: they delete the
-- August row, the next pipeline run re-inserts it.
--
-- Guarding on `budget_periods` being empty is NOT sufficient, which is only
-- visible when the SQL is actually executed: clear your *last* remaining cap and
-- the table is empty again, so the next run re-seeds every legacy row. The guard
-- held only while some unrelated cap happened to survive. The marker below
-- records that the one-time upgrade has happened, which is the thing we actually
-- mean, and it stays true no matter what the user later deletes.
--
-- Each legacy cap lands at the earliest month present in `transactions`, and
-- carry-forward inheritance covers every month after it -- so one row per
-- category reproduces the old "this limit applies always" behaviour exactly.
--
-- The column is `transaction_date`. `date` is only ever an ALIAS, introduced by
-- load_financial_data (app/dashboard.py:330, "t.transaction_date AS date") and
-- carried by the DataFrames built from it; it does not exist on the table. This
-- statement originally said `t.date` and so raised UndefinedColumn on every
-- startup, taking ensure_schema() -- and therefore migrations 001-029, which
-- share its single transaction -- down with it.
-- Records one-time data seeds so they stay done. Not a migration-version table:
-- ensure_schema() deliberately re-runs all DDL every call, and that stays true.
CREATE TABLE IF NOT EXISTS schema_seeds (
    name       TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO budget_periods (category, period, monthly_limit)
SELECT
    b.category,
    COALESCE(
        (SELECT to_char(MIN(t.transaction_date), 'YYYY-MM') FROM transactions t),
        to_char(NOW(), 'YYYY-MM')
    ),
    b.monthly_limit
FROM budgets b
WHERE NOT EXISTS (SELECT 1 FROM schema_seeds WHERE name = 'budget_periods_from_budgets')
ON CONFLICT (category, period) DO NOTHING;

-- Marked unconditionally, including on a fresh install with no legacy budgets:
-- the seed is a one-time upgrade of data that predates budget_periods, not a
-- standing sync. A `budgets` row saved from Streamlit afterwards is Streamlit's
-- own and must not appear here later.
INSERT INTO schema_seeds (name)
VALUES ('budget_periods_from_budgets')
ON CONFLICT (name) DO NOTHING;
