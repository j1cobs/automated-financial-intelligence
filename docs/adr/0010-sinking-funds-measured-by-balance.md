# ADR 0010: Sinking funds measured as required vs actual balance; the budget stays a tracking budget

## Status

Accepted (2026-10-20). Reaffirms ADR 0005's deferral of envelope rollover. To be implemented as PLAN.md
Phase 42.

## Context

The research (`docs/research/budget-tab-best-practices.md` §1.1, §1.6) found that every envelope-style
tool handles irregular costs (an annual tax, an insurance premium, car repairs) by rolling a per-category
balance forward: set aside $100 a month and the category holds $600 by month six. ADR 0005 deferred
rollover because it "only pays off under daily discipline". Adding sinking funds reopened the question.
Do they need a per-category balance after all?

A rollover balance is the running sum of every month since a start month. On this ledger that sum is
unstable. Plaid revises transactions in place (ADR 0003), the user flags Duplicates after the fact
(ADR 0002), and a category correction backfills older rows (ADR 0004). Each of these silently changes
every later month's balance. A virtual balance also asserts money exists that the app cannot see: "$600
in Car repairs" stays true on screen after the cash was spent on something else.

## Decision

**The budget stays a tracking budget.** Caps are limits that reset each Budget period. There is no
rollover and no "assign only money you have".

**A Sinking fund has no balance of its own.** It is an amount, a cadence and a next due date, held in a
nominated Account. For each Account, `analytics/sinking_funds.py` computes the **Required balance**: how
much every fund on that Account should hold by today. A fund due every 12 months with 5 months elapsed in
its cycle should hold 5/12 of its amount. The Required balance is compared with the Account's real balance
from `account_balance_snapshots`, giving a funded ratio per Account. Nothing is stored, so nothing can
drift.

**Saved this month** is the net balance growth of the Accounts nominated by Savings goals and Sinking
funds, the same measurement ADR 0008 uses for goal progress. Internal transfers, and credit-card payments
in particular, remain transfers. `classify_tx_type` and `detect_internal_transfers` are not weakened, so
moving money between the household's own Accounts is never spending and never income. It can only appear
as a balance change on a nominated Account.

## Consequences

- No per-fund progress bars. The honest unit is the Account: "Savings holds $1,310 against $1,235
  required". Per-fund status is derived by ordering funds by due date against that balance, and labelled as
  derived.
- A household that keeps sinking-fund money in its everyday chequing account gets a Required balance it
  cannot meaningfully compare. The UI says so instead of reporting a misleading funded ratio. Opt-in
  rollover remains a possible future addition, computed and never stored, if that case turns out to be
  common.
- Interest and market moves on a nominated Account count as "saved". The basis is labelled, as ADR 0008
  requires for a pace.

## Alternatives considered

- **Opt-in per-category rollover** (Actual's tracking mode, Lunch Money, Copilot). Lets money sit in the
  same account it is spent from, but the balance is virtual and unstable on a revised ledger.
- **A Savings goal that resets each cycle.** Per-fund bars, but the baseline re-capture misfires when a
  payout lands late, early or from another Account.
- **Set-aside as a budget line judged by transfers.** No balance check at all. A transfer made and then
  spent looks funded.
- **Full envelope budgeting.** The most power and the most machinery, plus a daily assignment routine the
  dashboard exists to avoid.
