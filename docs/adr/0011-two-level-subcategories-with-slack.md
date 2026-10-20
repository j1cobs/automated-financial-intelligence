# ADR 0011: Exactly two levels — curated Subcategories under Categories, with Unallocated slack

## Status

Accepted (2026-10-20). To be implemented as PLAN.md Phase 39.

## Context

Caps are keyed on the closed canonical category set (ADR 0005), which can't express "Housing → Condo fees
/ Home insurance / Electricity". The Budget tab already expands each row into a read-only `pfc_detailed`
breakdown (Phase 29), but those ~104 Plaid values were judged too granular for categorization in ADR 0004,
and their names are Plaid's, not the household's.

Every surveyed tool uses exactly two levels (group → category). Deeper nesting is a common request, but no
surveyed tool has shipped it, and Actual's attempt (PR #5268) was closed unmerged. The open design
questions were where children come from, how a transaction lands in one, and how parent and child caps
relate.

## Decision

**Exactly two levels.** The existing Canonical category is the parent. A *Subcategory* is a user-defined
child of exactly one Category, drawn from a closed set the user curates (same orphan-row reason as ADR
0005: a typo must not create a permanent budget row). A Subcategory never has children.

**Assignment extends the cascade, and the user's pin wins.**
1. Merchant memory may pin a merchant to a `(Category, Subcategory)`.
2. Otherwise, a Subcategory that *claims* the transaction's `pfc_detailed` value takes it. Each detailed
   value is claimed by at most one Subcategory. A claim only applies when the transaction's effective
   Category is the claiming Subcategory's parent, so a user's Category correction is never overridden by
   a detail claim.
3. Otherwise, the transaction has no Subcategory and counts against its Category's slack.

Plaid detail stays a *suggestion source* in the UI ("you have $180 of GAS_AND_ELECTRICITY: create
Electricity?"). It is never the child list itself.

**Parent and child caps: sum-or-larger (the Lunch Money model).** A Category with no Cap of its own is
capped at the sum of its Subcategories' Caps. A Category Cap at or above that sum leaves the difference
as *Unallocated slack*, which absorbs spending with no Subcategory. A Category Cap below the sum shows a
validation warning but does not block the save, because the user may be mid-edit.

**Subcategory Caps follow ADR 0005 exactly**: explicit rows per month, inheritance forward, clearing falls
back to inheritance. They are stored in a **sibling table** `subcategory_budget_periods`, not as a
nullable column on `budget_periods`. Postgres treats NULLs as distinct under `UNIQUE`, so `UNIQUE
(category, subcategory, period)` would allow two parent rows for one month.

## Consequences

- `update_transaction_category` gains an optional Subcategory. The per-transaction column
  (`user_subcategory_id`) joins `user_category`, `is_recurring` and `is_duplicate` as columns
  `upsert_transactions` must never name.
- Deleting a Subcategory that has Caps or pins is refused until they are moved or cleared, the same
  orphan-row reasoning again.

## Alternatives considered

- **Plaid detailed values as the children.** No curation needed, but too granular, Plaid-named, and two
  merchants sharing a detail (condo fees vs rent) can't be split.
- **Merchant pins only.** Never wrong, but almost everything lands in slack until hand-pinned.
- **Independent parent and child caps.** Two limits that can disagree, with no rule for which one a
  spend breaches.
- **An arbitrary tree.** No precedent, recursive aggregation everywhere, and a UI cost for every row.
