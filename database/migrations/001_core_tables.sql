CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    account_key TEXT NOT NULL UNIQUE,
    account_name TEXT NOT NULL,
    owner_name TEXT,
    official_name TEXT,
    account_type TEXT,
    account_subtype TEXT,
    balance_available NUMERIC(12,2),
    balance_current NUMERIC(12,2),
    balance_limit NUMERIC(12,2),
    iso_currency_code TEXT,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    external_id TEXT,
    transaction_hash TEXT NOT NULL UNIQUE,
    account_key TEXT NOT NULL REFERENCES accounts(account_key),
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    balance NUMERIC(12, 2),
    category TEXT,
    outlier_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    is_outlier BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_transactions_outlier ON transactions(is_outlier);
