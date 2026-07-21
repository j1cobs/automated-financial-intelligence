-- Defence in depth: transaction_hash is a Python-side string of the natural key, so any
-- future change in how a field is stringified can silently produce a "new" transaction.
-- This index makes Postgres compare the natural key directly (NUMERIC to NUMERIC, DATE to
-- DATE), so drift raises a unique violation instead of duplicating a row.
CREATE UNIQUE INDEX IF NOT EXISTS transactions_natural_key
    ON transactions (account_key, transaction_date, description, amount);
