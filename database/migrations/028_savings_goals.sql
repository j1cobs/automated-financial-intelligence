-- Phase 33: generic savings goals.
--
-- Deliberately knows nothing about what the money is for. A down payment, a
-- car, an emergency fund and a retirement pot are the same shape; the property
-- purchase that prompted the feature is one instance, not a special case.
--
-- `baseline_amount` is the combined balance of the linked accounts at the
-- moment the goal was created, so progress measures growth SINCE the goal
-- started rather than counting money that was already sitting there.
CREATE TABLE IF NOT EXISTS savings_goals (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    target_amount   NUMERIC(12,2) NOT NULL,
    target_date     DATE,
    baseline_amount NUMERIC(12,2) NOT NULL DEFAULT 0,
    started_on      DATE NOT NULL DEFAULT CURRENT_DATE,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Which accounts hold a goal's money. No UNIQUE on account_key alone: an
-- account may legitimately back several goals (one savings account funding both
-- a down payment and an emergency fund). That overlap is surfaced as a
-- "contested" amount rather than forbidden -- see analytics/goals.py.
CREATE TABLE IF NOT EXISTS savings_goal_accounts (
    goal_id     BIGINT NOT NULL REFERENCES savings_goals(id) ON DELETE CASCADE,
    account_key TEXT NOT NULL,
    PRIMARY KEY (goal_id, account_key)
);

CREATE INDEX IF NOT EXISTS idx_savings_goal_accounts_account
    ON savings_goal_accounts(account_key);
