-- Add manual-override category column; pipeline never writes this column
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_category TEXT;

-- Seed canonical personal-finance categories
INSERT INTO categories (name) VALUES
    ('ATM'),
    ('Dining'),
    ('Entertainment'),
    ('Groceries'),
    ('Health'),
    ('Housing'),
    ('Income'),
    ('Savings'),
    ('Shopping'),
    ('Subscriptions'),
    ('Transfer'),
    ('Transport'),
    ('Travel'),
    ('Uncategorized'),
    ('Utilities')
ON CONFLICT (name) DO NOTHING;
