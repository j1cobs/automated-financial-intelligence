# ADR 0002: Transaction identity is Plaid's transaction_id, and duplicates are not a schema constraint

## Status

Accepted (2026-07-27). Supersedes the duplicate-prevention rationale in migration 005.

## Context

The pipeline accumulated duplicate transactions. Investigation found three distinct mechanisms:

- **A** — the same Plaid `transaction_id` stored under two `account_key`s, after Plaid re-attributed 60
  transactions from one chequing account to another.
- **B** — a co-owned account exposed through *both* owners' Plaid Items, each Item issuing its own
  `transaction_id`s for the same real transactions.
- **C** — Plaid returning the same real transaction twice, with two `transaction_id`s.

The obvious fix for all three is a UNIQUE index on `(account_key, transaction_date, description, amount)`.
Migration 005 shipped exactly that.

**It is wrong, and this is the decisive fact:** the account holder made four separate, real `IKEA $250.00`
charges on 2026-07-02, tapping repeatedly against a $250 contactless limit. Under 005, three of those four
real charges are silently destroyed.

Worse, mechanism C is indistinguishable from that legitimate case. Every attribute Plaid exposes was compared
across all 9 duplicated groups in a 90-day window — `pending`, `pending_transaction_id`, `authorized_date`,
`authorized_datetime`, `payment_channel`, `transaction_code`, `merchant_entity_id`, `website`. In every group
the copies are identical on all of them; only `transaction_id` differs. There is no signal in the data that
separates a genuine repeat from a double-post.

## Decision

**Transaction identity is Plaid's `transaction_id`.** `build_transaction_hash` hashes it when present, falling
back to `account_key|date|description|amount` only for rows without one (seed data, future non-Plaid sources).

**No schema constraint attempts duplicate detection.** The account-scoped natural key is dropped (migration
010; 005 is now an intentional no-op) and must never be recreated. `transaction_hash` carries a UNIQUE
constraint, so whatever it hashes is what the table can hold at most one of — an account-scoped formula caps
the table at one row per natural key and makes the IKEA case unrepresentable.

Duplicates are instead handled by three mechanisms matched to the three causes:

| Cause | Mechanism |
|---|---|
| A | `transactions_external_id`, a partial unique index on `external_id` (migration 009) |
| B | `PlaidIngestor.fetch_transactions` ingests each real account once per run, skipping one already claimed by an earlier token |
| C | A user-set `is_duplicate` flag (migration 012), set from the dashboard |

Plus `DatabaseClient.reconcile_transactions`, which runs after every upsert and trims stored copies down to the
number Plaid currently returns per natural key. This catches the residual case of a transaction returning under
a genuinely new `transaction_id` after an Item re-link.

Two safety properties are load-bearing and must not be weakened:

1. **A natural key Plaid returns zero of is never touched.** Plaid's window rolls forward and drops history the
   database legitimately still holds. Absence from a fetch is not evidence of duplication.
2. **Reconciliation deletes user-flagged rows first, then rows whose `external_id` Plaid no longer returns,
   then newest-first.** Keeping the *earliest* row instead caused the pipeline to delete the fresh current row
   and re-insert it on every run — an observed 43-in/43-out thrash.

## Alternatives considered

- **Keep the account-scoped natural key.** Rejected: destroys the four real IKEA charges, and cannot see
  mechanisms A or B anyway, since those span accounts or carry differing ids.
- **Auto-collapse with an exceptions allow-list.** Rejected: every future genuine repeat is silently deleted
  until someone notices and adds it — the same failure mode, just delayed.
- **Mirror Plaid exactly and do nothing about mechanism C.** Rejected as the default, though it is what the
  system does until the user flags a row. Totals stay inflated by roughly 11 rows.

## Consequences

- **Duplicate handling requires occasional human judgement.** Only the account holder knows whether four
  identical charges are four taps or one double-post. The dashboard has a "Possible duplicates only" filter to
  make the candidate set findable; in a 90-day window it is ~20 rows.
- **Flagged rows are hidden, never deleted**, so the judgement is always reversible.
- **User-owned columns must stay out of the upsert.** `user_category`, `is_recurring` and `is_duplicate` are
  absent from both the INSERT list and the `ON CONFLICT` update list in `upsert_transactions`; that omission is
  the only thing making manual edits survive a nightly run. There is a regression test asserting it.
- **The hash formula changed for the third time.** Per the Phase 2.7 amendment in `PLAN.md`, any change to hash
  inputs ships with `rehash_transactions()`, which recomputes every stored hash and dedupes collisions.
- **Circumstantial evidence not encoded anywhere:** 5 of the 9 duplicated groups fell on 2026-05-11, a day with
  only 17 transactions, which looks like an institution-side batch double-post. That is a hypothesis worth
  checking against a paper statement, not a rule worth implementing.
