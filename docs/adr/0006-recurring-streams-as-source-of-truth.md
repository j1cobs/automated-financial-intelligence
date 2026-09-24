# ADR 0006: Recurring streams as the source of truth, with the per-row flag as an override

## Status

Accepted (2026-09-24). Implemented as PLAN.md Phases 30–31.

## Context

`transactions.is_recurring` (migration 006) is a bare per-row boolean, set by a checkbox in the ledger. There is no concept of a *series*. Two consequences followed, and the user reported both.

**The same charge could be flagged recurring over and over.** Every occurrence of a monthly subscription is its own row with its own checkbox, so marking Netflix recurring in January says nothing about February. The user's report — "make recurring transactions not able to be checked as recurring multiple times" — reads as a validation gap but is structural: there is nothing for the flag to attach to except the row.

**Cadence was guessed from raw description strings.** `build_overview` grouped flagged rows by `description` and projected the next charge from the median gap between occurrences. Grouping on the raw string means `NETFLIX.COM` and `Purchase / NETFLIX.COM` are different charges, so the Upcoming Recurring Charges card listed near-duplicates.

Separately, Plaid offers `/transactions/recurring/get`, which does stream detection itself. Research (2026-09-23) confirms it is available in the US, Canada and the UK, is supported by the same institutions that support Transactions, and **works with existing access tokens** — no re-link, no update mode. Whether it is *entitled* on a given Plaid account is a dashboard setting this codebase cannot see.

## Decision

**A stream is the unit.** `recurring_streams` (migration 027) holds one row per detected series: merchant key, cadence, direction, last amount, predicted next date, status, source.

**Two producers, one shape.** `stream_id` is Plaid's own id on the Plaid path and `'local:<merchant_key>'` on ours. Both write the same columns, so persistence, the API and the UI are indifferent to which produced a row. This is what lets the entitlement question stay unresolved without blocking anything downstream.

**Local derivation is deliberately strict.** `analytics/recurring.py::derive_streams` groups on the existing `merchant_key()` from ADR 0004 and requires: at least two occurrences; a median gap falling inside a recognised cadence window (weekly / biweekly / monthly / annually, with windows wide enough for real billing drift but non-overlapping); and it drops the group entirely when the gap matches no window rather than inventing a cadence. Fewer than three occurrences is `early_detection` rather than `mature`, matching Plaid's own threshold, and the UI renders those as lower confidence.

The strictness is the point: a stream asserts "this will happen again, around then, for about this much". A false positive puts a charge on the user's Upcoming list that never arrives, which is worse than omitting a real one.

**`stream_id` must be derived, not generated.** Upserts key on it, so an unstable id would add a duplicate stream on every pipeline run. Pinned by `test_stream_ids_are_stable_across_runs`.

**The user's hand-set flag always wins.** Resolution order:

```
1. user override  (transactions.is_recurring set by hand)
2. stream membership
3. not recurring
```

The pipeline never clears a flag the user set — the same rule `user_category` and `is_duplicate` already follow, and breaking it for `is_recurring` alone would be a surprise. `NULL` means "ingested before this column existed", i.e. unknown, not False, so it falls through to stream membership rather than being read as a decision.

**Toggling a row in a stream toggles the stream.** `PATCH /streams/{stream_id}/recurring` sets the flag on every member transaction. This is the actual fix for the duplicate-flagging report.

**The two controls must look different before the click, not after.** A row in a detected series and a standalone row now render distinguishably ("series" vs "this row"), with aria-labels saying which. Previously both were an identical bare checkbox with different consequences — which is how the same charge came to be flagged repeatedly in the first place.

**Membership is resolved in Python, not SQL.** `merchant_key` is computed by `analytics/categorizer.merchant_key`, not stored as a column. Resolving membership in SQL would mean reimplementing that normalisation (strip `Purchase /`, trailing city/province, trailing store numbers) in a second place, where the two could drift apart.

## Consequences

**The Plaid entitlement is still unverified.** `scripts/probe_plaid_recurring.py` reports whether `/transactions/recurring/get` is enabled, and has **not been run** — it needs live credentials. Until then local derivation is the active path. If the probe reports the add-on is available, `PlaidIngestor.fetch_recurring_streams` can take over without changing the table or anything downstream. Plaid sees more history than our rolling 90-day window, so it would likely detect more streams.

**The legacy median-gap projection is kept as a fallback**, extracted to `api/viewmodels.py::_upcoming_from_median_gaps`. It runs only when no streams exist at all — the first run after migration 027, or an account with no periodic spend. It is strictly worse (it groups on raw description) and exists so the card is not blank.

**Income streams are excluded from Upcoming Recurring Charges.** The card is about money leaving; including payroll made it read as though income were a bill.

**A stale prediction rolls forward rather than showing a past date.** A missed or late charge would otherwise leave a date in the past on a card headed "Upcoming".

**Toggling recurring now invalidates analytics.** This uncovered a pre-existing bug: `web/src/lib/mutations.ts` skipped the analytics invalidation on the grounds that no aggregate read `is_recurring`. That had stopped being true — `build_overview` reads it for the Committed/Recurring Spend card (`api/viewmodels.py:800`), exactly the case the old comment warned about — so that card kept showing a figure the toggle had already changed. Its test asserted the wrong behaviour and was corrected.

**Stream detection cannot fail the pipeline.** It runs after persistence inside a `try/except`: streams are an enrichment over rows that are already committed, so a detection failure is logged (exception class only, per the scrubbed-logging rule) and the run still succeeds.

## Alternatives considered

- **Depend on Plaid only.** Less code and better detection, but blocked on an entitlement nobody has confirmed, and it covers only Plaid-sourced accounts.
- **Derive locally only, ignore Plaid.** No entitlement risk, but rebuilds detection Plaid does better over more history.
- **Fix only the per-row flag** (prevent re-checking, de-duplicate the Overview list). Minimal change, but the underlying model stays incapable of saying when the next charge is due.
- **Retire the per-row checkbox entirely** once streams exist. Cleanest final model, but it would drop any flag that matches no stream — including charges Plaid missed and non-Plaid sources.

## See also

- `analytics/recurring.py` — derivation, cadence windows, `resolve_is_recurring`, `upcoming_from_streams`.
- `scripts/probe_plaid_recurring.py` — the entitlement probe, with the scrubbed logging the daily pipeline requires.
- ADR 0004 — `merchant_key`, the normalisation streams are grouped on.
