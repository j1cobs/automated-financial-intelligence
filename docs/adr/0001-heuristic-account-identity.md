# ADR 0001: Account identity is heuristic, not pinned

## Status

Accepted (2026-07-26)

## Context

Plaid re-issues a new `account_id` for the same real Account whenever a Plaid Item is re-linked
(e.g. after rotating an access token). `canonicalize_account_keys` (`database/db.py`) exists to
recognise that the new incoming account is the same one already stored, so history merges instead
of forking.

Plaid's own stable cross-relink identifier, `persistent_account_id`, is unavailable here: it is
NULL on every account in this database, because Desjardins (the institution behind most of these
accounts) does not supply it. With that primary signal gone, identity has to be inferred from
account metadata: `official_name`, `account_subtype`, `account_type`, and `mask`.

This is a heuristic, not a durable identifier. On 2026-07-10 a re-link forked two of Jacob's
Desjardins chequing accounts into duplicate `accounts` rows with split transaction history,
because both legacy rows had a NULL `mask` (predating that column) and shared every other field —
the heuristic had no way to tell them apart, and silently gave up rather than guessing wrong.

## Decision

Keep account identity heuristic — `(official_name, account_subtype, account_type, mask)` — rather
than introducing a pinned, assign-once internal identifier. Repair the immediate failure by
backfilling `mask` from the account name and preferring an exact mask match when the heuristic
would otherwise be ambiguous.

`owner_name` is excluded from the identity key. It records which Plaid access token revealed the
account, not who owns it — including it would prevent a jointly-held account seen through two
different tokens from ever being recognised as the same Account.

## Alternatives considered

- **Pin a durable local identity, assign-once.** On first sight, mint a stable internal id for
  each Account and store it; thereafter match directly on that id instead of recomputing the
  metadata tuple. This would stop a metadata rename from re-forking an *already-matched* Account,
  but the heuristic is still needed at the moment of a re-link to attach the newly-issued
  `account_id` to the existing identity in the first place — it narrows the fragile window rather
  than closing it.
- **Full surrogate-key refactor.** Introduce an internal account uid, repoint
  `transactions.account_key` at it, and treat the Plaid `account_id` as a per-Item connection
  detail rather than the primary key. This is the architecturally clean answer — merges become
  unnecessary because history never hangs directly off a Plaid-issued key — but it is a schema
  migration touching ingestion, the dedup tooling, and every dashboard join.

Both were deferred as disproportionate for a two-person personal-finance app. This ADR exists so
that judgement isn't silently re-litigated if the heuristic fails again.

## Consequences

- The residual risk is real and understood: if Plaid ever changes `official_name` for an existing
  Account (a rename, not a re-link), the identity key changes and the account can fork again. The
  dashboard now warns (`_section_net_worth` in `app/dashboard.py`) when any two `accounts` rows
  share an identity key, so a future fork is visible immediately rather than silently accumulating
  duplicate transactions for weeks.
- If this heuristic fails a second time, or if the institution mix grows to include one that
  supplies `persistent_account_id` unreliably, revisit the "pin a durable local identity" option
  above rather than patching the heuristic further.
- The fork warning only detects **over-forking** — multiple `accounts` rows sharing one identity
  key. It cannot detect the opposite failure, **under-merging**: two genuinely different Accounts
  whose identity keys happen to coincide, collapsing onto one `accounts` row. An under-merge
  destroys the very multi-row signal the check counts, so there is nothing for it to flag. Hardening
  this was considered and deliberately deferred (2026-08-24, see `PLAN.md` Phase 16, item 10) — it
  is a real-in-principle risk that has never been confirmed in practice, not a blocker.
