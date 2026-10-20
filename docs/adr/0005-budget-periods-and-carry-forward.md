# ADR 0005: Per-month budget caps with carry-forward inheritance

## Status

Accepted (2026-09-24). Implemented as PLAN.md Phase 28.

## Context

The user asked for the Budget tab to become the dashboard's primary instrument — something anyone wanting control of their finances could use to set, track, visualise and plan a budget. It could not become that, for a structural reason rather than a UI one.

`database/migrations/002_budgets.sql` defines:

```sql
CREATE TABLE budgets (
    id             BIGSERIAL PRIMARY KEY,
    category       TEXT NOT NULL UNIQUE,
    monthly_limit  NUMERIC(12, 2) NOT NULL,
    ...
);
```

`category` is UNIQUE, and there is no month. One row per category, for all time. "Budget $300 for Dining in October, $400 in December" is not expressible, and neither is "what was I budgeting last March?". `api/viewmodels.py::build_budget` read the table into a flat `{category → limit}` map and compared it against the current month only.

Anything beyond a retrospective scorecard — history, a forward forecast, a goal plan — needs the month dimension. The cost of adding it is the same whether the destination is per-month caps, envelope budgeting, or a forecast, so the schema change is unavoidable rather than optional.

## Decision

**A new `budget_periods` table keyed `UNIQUE (category, period)`**, where `period` is `'YYYY-MM'`. It stores only the months a cap was **explicitly set in**.

**Months with no row inherit the most recent explicit cap before them.** `analytics/budget_periods.py::resolve_caps` resolves a month; it is pure and DB-free, because the inheritance rule is small and easy to get subtly wrong.

```
Aug: Dining $400  (explicit row)
Sep: Dining $400  (inherited)
Oct: Dining $300  (explicit row, edited)
Nov: Dining $300  (inherited)
```

Set a cap once and it holds until changed. Editing a month writes a row for that month alone, so a later edit never rewrites history — `test_a_later_cap_does_not_leak_backwards` pins this.

**An absent cap is not a cap of zero.** A category nobody has budgeted is *absent* from `resolve_caps`' result and renders "No budget set". A category deliberately capped at `0` is present with value `0`, and any spend against it is over budget. The old code used `if limit:` for both, so a zero cap silently behaved like no cap at all. `build_budget` now branches on `is None`.

**The one-time seed from the legacy table is guarded on an empty table.** `DatabaseClient.ensure_schema()` re-runs *every* `.sql` file on *every* call. An unguarded seed would therefore resurrect a cap the user had deliberately cleared: delete the August row, and the next pipeline run puts it back. Migration 026's `INSERT ... WHERE NOT EXISTS (SELECT 1 FROM budget_periods)` is evaluated against the statement-start snapshot, so either every legacy row seeds (first run, empty table) or none do. `tests/test_budget_periods.py::MigrationSeedGuardTests` asserts the guard's presence, because the SQL itself cannot be executed under this repo's mocked DB layer.

**Caps are keyed on a closed category set.** `update_transaction_category` previously accepted arbitrary free text, so the effective category set was the 18 canonical names from migration 023 *plus every string ever typed*. Tolerable while a category was only a label; not once budget caps are keyed on it, since a typo creates a permanent orphan budget row. `analytics/categories.py::canonicalize` normalises case, spacing and the Phase-1 legacy names, and the endpoint rejects anything it cannot map unambiguously. It does no fuzzy matching and never falls back to `OTHER` — its output can rewrite a correction the user made by hand, and a wrong guess destroys what they meant.

## Consequences

**`budgets` is left entirely alone, and is now Streamlit-owned.** This is the part most likely to be got wrong later. The frozen Streamlit dashboard does not merely *read* that table — it **writes** it, at `app/dashboard.py:1186`, behind a "Save budgets" button. An earlier draft of this design mirrored the resolved caps back into `budgets` so both dashboards would agree. That would have silently discarded any budget saved from Streamlit on the next pipeline run. Nothing in the new path reads or writes `budgets`; `tests/test_budget_periods.py` asserts the migration never does either.

The two dashboards therefore show independent budget numbers. That is the accepted cost of the freeze: no edit is ever destroyed, which matters more than agreement between a primary UI and a fallback.

**The HTTP parameter is `month`, not `period`.** The filter bar already owns `period` as a query parameter, and its values are presets (`all_time`, `last_3_months`). A second `period` meaning `'YYYY-MM'` shadowed it and turned every filtered budget request into a 422 — caught by an existing test. The storage column and the domain term stay `period`; only the HTTP name differs, and only for that reason.

**Clearing a cap falls back to inheritance, not to zero.** `DELETE /budgets/{category}?month=` removes the explicit row; the month then inherits again. This is the only way to undo an edit without asserting a $0 budget.

## Alternatives considered

- **Keep the flat table, improve only the UI.** No schema change, but no history, no forward planning, and no foundation for the forecast (ADR-adjacent, PLAN.md Phase 32) or goals (ADR 0008).
- **Explicit cap per month, no inheritance.** Maximum clarity about what was actually committed to, but real monthly data entry, and an unset month is indistinguishable from a $0 budget at a glance.
- **A template plus per-month overrides.** Closest to the existing flat table, but introduces a second concept ("the default budget" vs "this month's budget") to reason about, for the same expressive power inheritance already gives.
- **Full envelope / YNAB budgeting** (rollover of unspent funds, cross-category reallocation). Materially more powerful and materially more machinery — a per-month-per-category balance ledger — and it only pays off under daily discipline. Explicitly deferred; the user had not yet used the budget tab at all.

## See also

- `analytics/budget_periods.py` — `resolve_caps` / `resolve_caps_detailed`.
- `analytics/categories.py` — the closed category set and conservative normalisation.
- `database/migrations/026_budget_periods.sql` — the guarded seed.
- `scripts/normalize_user_categories.py` — dry-run cleanup of pre-existing free-text corrections, deliberately a script rather than a migration for the same re-run reason.
