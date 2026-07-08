CREATE TABLE IF NOT EXISTS budgets (
    id             BIGSERIAL PRIMARY KEY,
    category       TEXT NOT NULL UNIQUE,
    monthly_limit  NUMERIC(12, 2) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
