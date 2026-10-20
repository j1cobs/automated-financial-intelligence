# ADR 0008: Goal progress measured from account balances, and a pace that always states its basis

## Status

Accepted (2026-09-24). Implemented as PLAN.md Phase 33.

## Context

The user is looking to buy a property and wanted the dashboard to help plan for it. The first design question was whether to build a *home-purchase* feature. The user's own correction settled it: the tool must be generalisable — "the user must be able to set a goal no matter the reason (home purchase, car purchase, saving, retirement...)". So: generic savings goals, of which a down payment is one instance. Nothing in the schema or the UI knows what a house is.

The second question was how Plaid could help, and the answer is mostly that it cannot. Research (2026-09-23) found that the products which would supply lender-grade documentation — Asset Reports, Bank/Payroll Income, Statements — are Plaid's US lending stack; Canadian availability is unconfirmed and Assets additionally cannot be added after the initial Link at all. This household banks with Desjardins and BNC. Anything useful therefore has to be built from data already held.

The third question is the one this ADR exists for: **what does "saved so far" mean?**

## Decision

**Progress is linked account balances minus a baseline captured when the goal was created.**

The user nominates the accounts that hold the goal's money. At creation, their combined current balance is stored as `baseline_amount`, so progress measures growth *since the goal started* rather than crediting money that was already sitting there.

**Progress is deliberately not floored at zero.** If the balance falls below the baseline, the user has spent goal money — which is precisely the situation they most need to see. Clamping it to 0 would hide it.

**A pace is never surfaced without its basis.** `analytics/goals.py::pace` returns `(amount_per_month, basis, weeks_of_history)`, and the UI renders all three. `basis` is `"balance"` once there are at least 12 weeks of snapshots and `"cashflow"` below that.

This matters because `account_balance_snapshots` only began collecting around 2026-08-25 (migration 017, PLAN.md Phase 17). Balance-derived growth therefore has roughly a month of history today, and a figure computed from four weeks that *looks* exactly as authoritative as one computed from a year is worse than showing no figure at all.

**The switch is hard, not blended.** An earlier draft of this design said "blend, show confidence" and then specified a hard switch — a contradiction caught when the plan was grilled against itself. Resolved in favour of the hard switch: one number with one stated provenance, which a reader can reconstruct, beats a weighted figure nobody can. `test_the_switch_is_hard_not_blended` pins it.

**Account overlap between goals is allowed, but surfaced.** One savings account can back both a down payment and an emergency fund — people really do save for two things in one place, and forbidding it would force the user to open an account to model something they already do. But left unsaid, the dashboard would report both goals on track when the same dollars can only buy one. So `contested_amounts` reports, per goal, how much of its balance sits in an account another goal also claims, and the UI says so on the row.

**A zero pace yields no projected date.** Dividing by it produces infinity, not a date. `on_track` is likewise `None` when there is no target date to be on track against — the absence of a judgement is itself information, and inventing `false` would be a claim.

**`what_if(goal, category, monthly_reduction)`** re-projects with more going in each month. This is what makes the tracker actionable rather than decorative: "cut dining by $200 and you hit the target in February instead of April" is a decision; a progress bar is only a status.

## Consequences

**The user must nominate accounts for a goal to track anything.** A goal with no linked accounts reports progress of `-baseline` (i.e. 0 − 0 for a fresh goal), which is honest but inert. The trade is deliberate: the alternative needs no setup and cannot be trusted.

**Goals live in the Budget tab, not a tab of their own.** The user asked for Budget to be the dashboard's primary instrument; splitting planning across two tabs works against that. Goals also share the forecast (PLAN.md Phase 32), whose horizon extends to cover the furthest goal's target date.

**Today every goal will show a cash-flow pace.** That is the correct reading of the data available, and the UI states the week count so the user can see it improving. Balance-derived pace becomes available roughly 12 weeks after the snapshots started.

**There is no affordability calculator.** Mortgage payment, property tax, insurance, condo fees and Quebec's welcome tax (*taxe de bienvenue*) were scoped and deferred: that feature is a form plus a formula, it shares nothing with this one, and none of its inputs come from Plaid.

## Alternatives considered

- **Derive progress from cumulative net cash flow** (income − expenses since the goal started). Needs no account selection and counts every dollar not spent. Rejected: it drifts from reality the moment money moves somewhere the dashboard cannot see, and it keeps counting money that was later spent. It survives only as the *pace* fallback, where it is labelled.
- **Manual contribution logging.** Accurate to intent and works for cash or outside accounts, but it is manual data entry — the thing this dashboard exists to avoid.
- **Forbid account overlap between goals.** Progress numbers would need no caveat, but it forces an account per goal to model ordinary behaviour.
- **Per-goal allocation splits** (percentage or fixed amount of a shared account). The most accurate model, and another thing to maintain that drifts as balances move.
- **Plaid Asset Reports / Income** for lender-grade figures. Out of scope on geography, per the research above.

## See also

- `analytics/goals.py` — progress, pace, projection, what-if, contested amounts.
- `database/migrations/028_savings_goals.sql` — why there is no UNIQUE on `account_key` alone.
- `tests/test_goals.py` — baseline exclusion, the hard switch at exactly 12 weeks, zero-pace handling, contested shares.
- ADR 0005 — the budget caps the forecast holds categories to.
