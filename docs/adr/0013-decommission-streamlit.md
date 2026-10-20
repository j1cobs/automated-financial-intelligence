# ADR 0013: Decommission the Streamlit dashboard

## Status

Accepted (2026-10-20). Supersedes the Phase 15 freeze ("Streamlit is frozen", PLAN.md archive), which kept `app/` as a reference implementation and fallback. Implemented as PLAN.md Phase 55. Amends ADR 0005 (`budgets` ownership) and ADR 0007 (the `is_outlier` shim).

## Context

Phase 15 froze the Streamlit dashboard: new work went to the React dashboard (`web/`, deployed on Vercel, with `/api/*` rewritten to the FastAPI service on Render), and `app/` was kept as a fallback nobody could edit. By Phase 54's design the freeze was costing more than the fallback was worth:

- The pipeline and the API imported the loader and the enrichment helpers from inside the frozen module, so a column the API needed could not be added to `load_financial_data`. `api/dataload.py` merged extra columns in after the fact instead, and Phase 37 would have needed another merge for `pending`.
- `api/filters.py` had to be maintained as a hand-written *port* of `_build_sidebar_filters`, a file nobody was allowed to touch.
- `budgets` counted as Streamlit-owned, because the frozen dashboard wrote it; nothing new could write it.
- `streamlit` and `plotly` stayed runtime dependencies (27 locked packages between them), alongside a second sign-in stack in `app/auth.py` and a `.streamlit/secrets.toml` configuration layer.

The React dashboard had reached parity (Phases 15-36), and the user decided on 2026-10-20 that the fallback could go.

## Decision

**Delete Streamlit, after relocating what the live paths still import.** Relocation came first and in its own commit, behaviour-identical, so the daily pipeline never depended on a deleted module:

- `load_financial_data` → `database/frames.py`.
- `classify_tx_type`, `detect_internal_transfers`, `enrich_transactions`, `effective_credit_limit` → `analytics/enrichment.py` (pure, no I/O; leading underscores dropped now that they are a public module's API).
- `_label_subtype` → `api/viewmodels.py`, its only remaining caller.

Then delete `app/`, the root `streamlit_app.py`, the Streamlit-only tests, `DatabaseClient.get_budgets` / `upsert_budget`, the two dependencies, and the `.streamlit/secrets.toml` layer. Configuration precedence becomes environment → `.env` → default.

## Consequences

**The `budgets` table stays, inert.** Migration 026's guarded seed reads `FROM budgets` and `ensure_schema()` re-runs it on every boot. Postgres resolves the table at plan time even when the guard is false, so dropping it would fail every entry point — the same failure mode as migration 026's original outage. The table is now legacy: nothing reads or writes it. Only its Streamlit-only DB methods were removed.

**`is_outlier` stays, re-described.** ADR 0007 kept it as a compatibility shim for the frozen dashboard. The React outliers-only filter (`api/filters.py`) and the flagged counts in `api/viewmodels.py` read it since, so it is now simply the flag on the rows behind a live anomaly. `DatabaseClient.set_outlier_flags` and its pipeline call are unchanged.

**The shared OAuth core stays.** `core/auth_session.py`, `core/google_oauth.py` and `oauth_pending_state` are used by the API's sign-in; only the Streamlit wrapper (`app/auth.py`) went.

**`.env` loading became unconditional.** It used to happen only in the branch where no secrets file existed, which is why removing the layer had to keep the `load_dotenv(..., override=False)` call rather than delete it with the function.

**`api/filters.py` is the source of truth**, not a port. Its three invariants (two frames, enrich-before-filter, whole-month periods) and their tests are unchanged.

**The French UI is lost for now.** Streamlit had an en/fr toggle; the React app is English-only. `web/src/lib/strings.ts` is built so a second locale is a translation pass over one module.

**The two dashboards no longer disagree about budgets.** ADR 0005 accepted independent budget numbers as the cost of the freeze; with one dashboard, that cost is gone.

## Alternatives considered

- **Keep the frozen fallback.** Zero work now, but every phase of the budget toolkit (37-54) would have designed around it: more `dataload` merges, a filters port drifting further from its source, and two runtime dependencies nothing live uses.
- **Extract the shared helpers but keep Streamlit running.** Removes the import coupling but keeps the second sign-in stack, the dependencies and the `budgets` ownership rule, for a fallback the user no longer opens.
- **Drop the `budgets` table too.** Cleaner schema, but it breaks migration 026 on every boot unless 026 is rewritten, and rewriting an always-re-run migration to stop reading a table is riskier than keeping an empty one.

## See also

- `database/frames.py`, `analytics/enrichment.py` — the relocated helpers; `tests/test_enrichment.py` carries their tests unchanged.
- ADR 0005 — `budgets` ownership, now amended.
- ADR 0007 — the `is_outlier` shim, now amended.
- PLAN.md Phase 55 (archived once verified) — the relocate / delete / docs checkpoints.
