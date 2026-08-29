-- Phase 18: adopt Plaid's personal_finance_category taxonomy wholesale. The live DB had split
-- 'Uncategorized' (754 rows) and 'uncategorized' (62 rows) into two separate category strings
-- -- confirmed by two independent probes -- because the lowercase one wasn't in the canonical
-- categories table at all. This migration collapses both onto 'UNCATEGORIZED' and reseeds the
-- categories table with the 17 primary values Plaid's own taxonomy uses (16 categories + OTHER),
-- observed with 100% coverage across every linked account (see Step 0 probe in the Phase 18
-- plan), plus 'UNCATEGORIZED' for non-Plaid sources (seed data, rows with no PFC match).
--
-- Re-run safety: the UPDATE only ever touches rows that are already NULL or already normalize
-- to 'UNCATEGORIZED', so re-running it against already-uppercase rows is a no-op. The DELETE
-- and INSERT are similarly idempotent (no-op once the old rows are gone / the new ones exist).
UPDATE transactions SET category = 'UNCATEGORIZED'
 WHERE category IS NULL OR upper(category) = 'UNCATEGORIZED';

DELETE FROM categories WHERE name IN ('Uncategorized', 'uncategorized');

INSERT INTO categories (name) VALUES
    ('FOOD_AND_DRINK'), ('GENERAL_MERCHANDISE'), ('INCOME'), ('TRANSFER_IN'), ('BANK_FEES'),
    ('TRANSPORTATION'), ('MEDICAL'), ('TRANSFER_OUT'), ('GENERAL_SERVICES'), ('LOAN_PAYMENTS'),
    ('PERSONAL_CARE'), ('OTHER'), ('HOME_IMPROVEMENT'), ('RENT_AND_UTILITIES'), ('ENTERTAINMENT'),
    ('TRAVEL'), ('GOVERNMENT_AND_NON_PROFIT'), ('UNCATEGORIZED')
ON CONFLICT (name) DO NOTHING;
