# ADR 0012: Account holder is distinct from Owner; per-person views and shared-cost settlement build on it

## Status

Accepted (2026-10-20). To be implemented as PLAN.md Phases 40 (members and holders) and 47 (settlement).

## Context

The household has two members, and both members' banks are already ingested through separate Plaid
tokens. The only per-person attribute in the data is `owner_name`, which records **which access token
revealed an Account** (CONTEXT.md, "Owner"), not whose Account it is. A joint chequing account is
therefore attributed to whichever member's connection happened to reveal it first. Since ingestion claims
each real Account once per run (CLAUDE.md, ingestion), that choice is effectively arbitrary.

The user chose one household budget with per-person views, plus shared-cost settlement. Building either
on `owner_name` would attribute joint spending to the wrong person, so the question was what to build on
instead.

## Decision

**Household members are a configurable list**, stored in the database and created in the setup wizard or
settings. They are never hardcoded as "me" and "partner", following CLAUDE.md's decoupling convention.

**Account holder** is a new, user-set attribute on each Account: one Household member, or *Joint*.
Per-person views filter spend and income through it, and joint Accounts show as their own slice. `Owner`
stays an ingestion detail and nothing user-facing reads it for attribution.

**Holder must survive the pipeline and Account forks**, the same way `manual_credit_limit` already does:
- `accounts` upserts never name the holder column.
- `merge_account` carries the holder onto the canonical row when the canonical row's holder is NULL.

**Caps, Plans and Savings goals stay household-level.** Per-person views filter what was spent and earned.
They never split a Cap.

**Shared-cost settlement** covers *Shared spending*, which is defined as:
- everything spent on a Joint Account;
- plus spending in Categories the household marks as **shared** (Housing, Groceries, Utilities), whatever
  Account paid it;
- plus or minus a per-transaction override either way.

Buying household groceries on a personal card is the case this exists for. With Shared spending defined:
- Each member's *fair share* comes from a household **share basis**: equal, proportional to Regular income
  (recomputed each Budget period), or a custom ratio. Equal and income-proportional are one-click presets.
- *Paid* is what each member actually put in. Shared spending on a member's own Account is paid by that
  member. Spending on a Joint Account is paid in proportion to what each member transferred into it
  during the period.
- A transfer from one member's Account to another member's counts as settlement and reduces the
  running balance. A transfer into a Joint Account counts as a contribution.

`analytics/settlement.py` is pure and states the share basis on every figure it returns.

## Consequences

- The user tags each Account once. Until then an Account's holder is NULL, and per-person views show it
  as "Unassigned" rather than guessing from `owner_name`.
- Detecting settlement needs the internal-transfer pairing `detect_internal_transfers` already does,
  read with holders attached. The pairing itself is not changed.
- A spend split between two members inside one transaction is expressed with a Split (PLAN.md Phase 48),
  not a new mechanism.

## Alternatives considered

- **Use `owner_name` as the holder.** No setup, and wrong for every joint Account.
- **Per-transaction person split** (a ratio on every joint transaction). The most accurate, and a value to
  maintain on every row.
- **Shared spending = Joint Accounts only.** Simple, but a household purchase on a personal card never
  counts, and that is the most common case.
- **Shared spending = a `#shared` Tag only.** Explicit, but manual for every grocery run unless rules
  cover it.
- **Separate budgets per member plus a joint budget.** Needs an owner dimension on Caps, Goals and Plans.
  The user chose one household budget.
