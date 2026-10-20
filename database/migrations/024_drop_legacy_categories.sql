-- Migration 023 removed the two case-variant 'Uncategorized'/'uncategorized' rows but left the other 14
-- Phase-1 (migration 003) category names in place, so every category-picking UI has shown both taxonomies
-- side by side with no visual distinction since Phase 18 shipped (e.g. "Dining" next to "Food and Drink").
-- Guarded, not a blind DELETE: a name is only removed if nothing currently references it in
-- transactions.category, transactions.user_category, budgets.category, or merchant_categories.category --
-- so this stays safe to re-run (ensure_schema() runs every migration on every call) even if some environment
-- has since budgeted or corrected against one of these names.
DELETE FROM categories
WHERE name IN (
    'ATM', 'Dining', 'Entertainment', 'Groceries', 'Health', 'Housing', 'Income', 'Savings',
    'Shopping', 'Subscriptions', 'Transfer', 'Transport', 'Travel', 'Utilities'
)
AND name NOT IN (SELECT category FROM transactions WHERE category IS NOT NULL)
AND name NOT IN (SELECT user_category FROM transactions WHERE user_category IS NOT NULL)
AND name NOT IN (SELECT category FROM budgets)
AND name NOT IN (SELECT category FROM merchant_categories);
