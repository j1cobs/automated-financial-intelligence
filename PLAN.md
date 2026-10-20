# Plan — open work

> **This file holds open work only.** Phases 0-36 are done, superseded or deferred, and live verbatim in
> [`docs/plan-archive.md`](docs/plan-archive.md), with the same phase numbers. Read the archive only for the
> history or rationale of a specific phase. Don't scan it for things to do: every item in it that was still
> open has been carried over below.
>
> **Conventions.** Phase numbers reflect the order things were *designed*. "Where things stand" ranks what
> to do next. When a phase ships, put a `> **Status (date):** ...` blockquote at its top noting deviations.
> Once its verification is done, move it to the archive. Work that ships outside the plan gets its own
> phase after the fact. Each phase stops uncommitted with a recommended commit title and body, and the
> user commits. New work is proposed by appending a phase here, not by implementing it.
>
> **Branch.** Feature work targets `dev`. `main` receives `dev` by merge.

---

## Where things stand (updated 2026-10-20, verified against the code)

**Done and archived:** Phases 0-6, 2.5-2.8, 3 (3a-3s), 4, 5, 8, 10-14, 16-18, 25, 26-35 (verified
2026-10-20: migrations 026-029, the budget/recurring/forecast/goals/anomalies modules with their tests,
`refresh_balances`, ADRs 0005-0008) and 36. Phase 7 is superseded by ADR 0007, and Appendix A is superseded
item by item (see "Ideas backlog").
**Implemented, verification open:** Phase 15 (live end-to-end pass, O4).
**Designed, not started:** Phase 55 (decommission Streamlit; lands first), then Phases 37-54 (Budget tab
toolkit and generic Plans).

### Recommended order of work

Ranked by what unblocks the most, not by phase number.

| # | Work | Why here | Effort |
|---|---|---|---|
| 1 | **O1 — README screenshots** | The public README embeds four images that were never committed, so it renders broken. | ~30 min |
| 2 | **O2 — Confirm scheduled automation is actually running** | Gates Phase 53 (digest), O5 (fallback removal), and the balance-basis goal pace (ADR 0008 needs 12 weeks of snapshots). Its status has flipped before without the docs noticing. | ~15 min |
| 3 | **Phase 55 — Decommission Streamlit** | Removes the frozen module that Phases 37-54 would otherwise work around (the loader, the filters port, `budgets` ownership), plus two runtime dependencies. Relocate first, then delete. | M |
| 4 | **Phase 37** — Budget quick wins | First of the foundations; small and visible (totals, over-by, pending, currency, notes, exclusions). | S-M |
| 5 | **Phases 38-39** — line classes, ratios, subcategories | Plans and ratios depend on line classes; Subcategory caps are the most-requested monthly feature. | M each |
| 6 | **O3 — Run `scripts/probe_plaid_recurring.py`** | Decides whether Plaid's add-on supplies recurring streams, including the *inflow* streams Phase 40 uses as Regular income. Run it before Phase 40. | ~15 min |
| 7 | **Phases 40-42** — household and income, tags, sinking funds | The rest of the foundations Plans depend on. | M each |
| 8 | **O4 — Phase 15 live verification pass** | Needs a signed-in owner session. Best done before Phase 45 changes the Budget tab's layout. | ~30 min |
| 9 | **Phases 43-46** — projection engine and Plans | The core of the spreadsheet replacement. | M-L each |
| 10 | **Phases 47-52, 54** — breadth | Settlement, splits and manual accounts, cap extensions, review surfaces, debts, XLSX, setup wizard. | M each |
| 11 | **O5 — Remove the `/transactions/get` fallback** | Only after O2 shows sync running clean in production for about 2 weeks. | S |
| 12 | **Phase 53** — email digest | Blocked on O2. | M |
| 13 | **O6, O7** — leftover verification and cleanups | Low risk, no user-visible change. | S |

---

## Open items carried over from archived phases

### O1 — README screenshots (from Phase 0)

`README.md:13` and `README.md:17` embed `docs/images/overview.png`, `cashflow.png`, `budget.png` and
`transactions.png`. Only `docs/images/README.md` is tracked, so all four images are broken on GitHub.
- Capture on **sample data only**: `python scripts/seed_sample_data.py` against `SEED_DATABASE_URL`, never
  `DATABASE_URL` (Phase 13 discipline). No real financial information may appear in a screenshot.
- Capture the React dashboard (`uvicorn api.main:app` + `cd web && npm run dev`). Rewrite the four
  captions to match the React tabs; the current ones describe the old dashboard (e.g. "inline category
  editing and anomaly flags"). Best done with Phase 55c's README pass.
- Keep the files small (PNG, ≤ ~300 KB each) and commit them under `docs/images/`.

### O2 — Confirm scheduled automation is actually running (from Phases 0, 5b, 14)

The workflow's own top-of-file comment still says it is inert until Secrets are set on `main`. Memory notes
show the status has flipped between live and inert before without `CLAUDE.md` catching up. Decide from
evidence, never from either document:
- `pipeline_runs`: count rows per day by `trigger_type` (`schedule` / `workflow_dispatch` / `local`), using an
  aggregate query only and never raw transaction content.
- `account_balance_snapshots`: date coverage and gaps.
- The Actions run history for `daily-finance-pipeline.yml` on `main`.

Then correct the Automation section in `CLAUDE.md` to match. If it is not running, the owner fixes Secrets
or the default-branch workflow; there is no code change.

### O3 — Run the Plaid recurring probe (from Phase 30)

`scripts/probe_plaid_recurring.py` is read-only and has **never been run**. Streams come only from
`analytics/recurring.py::derive_streams`, and `PlaidIngestor.fetch_recurring_streams` does not exist yet.
`pipeline/runner.py:214` documents the seam it would plug into.
- Run it with the production tokens. Its logging already follows the scrubbed rule (`status_code` /
  `error_type` / `error_code` only).
- If it is entitled, add `fetch_recurring_streams()` *alongside* the `BaseIngestor` seam (Phase 17
  discipline), producing the same table shape as `derive_streams`. If not, record the result in ADR 0006
  and close the item.

### O4 — Phase 15 live end-to-end pass (from Phase 15)

Automated checks were green when Phase 15 shipped. The signed-in pass against the live database never
happened:
1. Income vs. Expenses renders **actual bars**.
2. The savings-rate axis stays within ±100%.
3. Exactly one x-axis label per account holder on the owner-balance chart.
4. A keyboard-only tooltip pass on every KPI tile, at a narrow viewport.
5. A dark-mode sweep of every tab.

### O5 — Remove the `/transactions/get` fallback (from Phase 17, follow-up 1)

`PlaidIngestor.fetch_transactions` (`ingestion/plaid_ingestor.py:333`) is kept only as a rollback path from
`sync_transactions`. Remove that Plaid-specific path once O2 shows about 2 weeks of clean production
sync runs (stable cursors in `plaid_sync_state`, no crash eating deltas). **`BaseIngestor.fetch_transactions`
stays.** It is the interface seam for future non-Plaid sources (`CLAUDE.md`, ingestion). Update
`CLAUDE.md` and the Phase 17 references in the same change.

### O6 — Phase 14 verification never run (from Phase 14)

1. Run `python main.py` against a disposable/local database (never prod) and confirm a `pipeline_runs` row
   lands with the right counts and `status='success'`.
2. Force a failure path (a bad `DATABASE_URL` for the `OperationalError` branch, or a bad Plaid token for
   `requests.RequestException`). Confirm `pipeline_runs` gets a `status='failed'` row with a
   non-transaction error message, and that stdout shows no response body or mask.

### O7 — Low-priority cleanups (from Phase 12)

- `upsert_transactions`' docstring still partly describes the pre-Phase-12 account-scoped hash and its
  removed relocation pass. The inline comment below it is correct.
- Migrations 008 and 011 are one-off cleanups that run on every `ensure_schema()` call. They are
  idempotent, so this is correct but not free. Revisit if the migration list keeps growing (Phases 37-54
  add 030-042).

### Deferred by decision (do not start without the user)

- **6h — `pytest` as the runner.** Optional; the `unittest` suite already runs under it. See the archive for
  the `pyproject.toml` snippet.
- **Phase 16 item 10 — account-fork banner under-merge hardening.** A documented known limitation (ADR 0001),
  never implicated in a real bug.
- **Phase 18 follow-ups:** layer 3 (TF-IDF) waits for evidence of a coverage gap, and `category_source =
  'user'` is reserved but unwritten. Pending-in-the-UI moved to Phase 37, and `pfc_detailed` is surfaced
  by Phase 29 and suggested by Phase 39.

### Ideas backlog (from Appendix A)

Not covered by any phase yet:
- **A2 — Transaction notes:** a free-text note per transaction (`transactions.user_note`, pipeline never
  writes it).
- **A3 — Category confirm / review:** a `category_status` flag (`confirmed` / `review`) per transaction.
  It would be a triage queue for low-confidence PFC rows (Phase 18 found 67% at LOW confidence).

Superseded: A1 budget notes → Phase 37; A4 anomaly dismiss → Phase 34; A5 exclude from analytics → Phase 37
(Excluded categories) and Phase 48 (reimbursables); A6 merchant rules → Phase 18 merchant memory; A7 savings
goals → Phase 33; A8 category management → the closed set (ADR 0005) plus Subcategories (Phase 39); A9 split
transactions → Phase 48; A10 recurring tagging → Phases 30-31.

---

## Standing constraints (still live; from the archived "Ordering constraints / risks")

- **Don't change `build_transaction_hash` inputs without a rehash + dedup migration.** Re-ingest idempotency
  depends on them. They were superseded three times, each deliberately and each shipped together with
  `rehash_transactions()` (Phases 2.7, 2.8, 12b).
- **Seed data must use the Plaid sign convention** (positive = outflow), or cash flow inverts.
- **`load_settings()` must never hard-require Plaid credentials.** That would break the seed demo and
  dashboard-only deployments. Plaid validation lives only in `pipeline/runner.py::_build_ingestor`.
- **Seeding is `SEED_DATABASE_URL`-only.** Confirm it points at a non-production database before every
  `seed_sample_data.py` run (Phase 13).
- **Never run `python main.py` as casual verification.** It hits live Plaid and writes production data. Use
  the seed script, or a disposable database as in O6.
- **The CI gate:** `ruff check . && ruff format --check .`, the Python suite, and the four web checks in
  `CLAUDE.md` all stay green (Phases 5 and 8a).

---

## Phase 55 — Decommission Streamlit

> **Status:** designed, not started. The user decided on 2026-10-20: "we can decommission it". **Lands before
> Phase 37**, so Phases 37-54 build on code with no frozen module in the way. After this phase the React
> dashboard is the only one: `web/` is deployed on Vercel, and `web/vercel.json` rewrites `/api/*` to the
> FastAPI service on Render.
>
> Three commit checkpoints: **A** relocate, **B** delete, **C** docs. The suite must be green at A before
> anything is deleted.

### Why this work

Streamlit has been frozen since Phase 15 and kept only as a fallback. Keeping it costs real design effort:
- The frozen `load_financial_data` forces the column merges in `api/dataload.py` (and Phase 37's planned
  `pending` merge).
- `api/filters.py` has to be maintained as a hand-written *port* of a file nobody may edit.
- `budgets` is "Streamlit-owned" and may not be written.
- `streamlit` and `plotly` stay as runtime dependencies.
- There is a second sign-in stack (`app/auth.py`), and the docs describe the wrong dashboard.

### What this phase must not break (found while scoping, 2026-10-20)

1. **The pipeline and the API import from `app/dashboard.py`:**
   - `pipeline/runner.py:14` (`_enrich_transactions`, `load_financial_data`);
   - `api/dataload.py:33` (`load_financial_data`);
   - `api/viewmodels.py:55-59` (`_effective_credit_limit`, `_enrich_transactions`, `_label_subtype`);
   - `tests/test_pipeline_history.py:23`.

   Deleting `app/` first breaks the daily pipeline, so 55a relocates these before anything is deleted.
2. **`is_outlier` is not Streamlit-only any more.** `api/filters.py:211` (the outliers-only filter) and
   `api/viewmodels.py:669` / `:1115` (flagged counts) read it, and `web/src/lib/metricInfo.ts:128` documents
   it. `DatabaseClient.set_outlier_flags` and its call in `pipeline/runner.py` therefore **stay**. They are
   re-described as "flags the rows behind live anomalies", no longer as a Streamlit compatibility shim.
3. **`budgets` (migration 002) cannot be dropped.** Migration 026's guarded seed does `... FROM budgets b`
   and re-runs on every `ensure_schema()`. A missing table fails at plan time, even with the guard false.
   That is the same failure mode as migration 026's original outage, and it takes down every entry point.
   The table stays, inert and documented as legacy; only its Streamlit-only DB methods go.
4. **`core/auth_session.py`, `core/google_oauth.py` and `oauth_pending_state` (migration 016) are shared with
   the API** (`api/security.py:16`, `api/routers/auth.py:18`, `:79`). They stay, together with
   `tests/test_auth_session.py` and `tests/test_google_oauth.py`.
5. **The French UI is lost.** Streamlit had an en/fr toggle; React is English-only. `web/src/lib/strings.ts`
   is built so a second locale is a translation pass over one module. That pass is **not** part of this
   phase.

### 55a — Relocate the shared helpers (checkpoint A)

Move these verbatim, with behaviour identical, so only imports change:

| From `app/dashboard.py` | To | Name after the move |
|---|---|---|
| `load_financial_data` (both SELECTs unchanged, still `t.transaction_date AS date`) | `database/frames.py` | `load_financial_data` |
| `_detect_internal_transfers`, `_classify_tx_type`, `_enrich_transactions`, plus `_PAYMENT_KEYWORDS`, `_REFUND_KEYWORDS`, `_TRANSFER_MATCH_DAYS` | `analytics/enrichment.py` (pure, no I/O) | `detect_internal_transfers`, `classify_tx_type`, `enrich_transactions` |
| `_effective_credit_limit` | `analytics/enrichment.py` | `effective_credit_limit` |
| `_label_subtype` + `_SUBTYPE_LABELS` (presentation) | `api/viewmodels.py` | `_label_subtype` (private) |

- Repoint the four importers in "must not break" item 1.
- **Tests move with the code, assertions unchanged.** All 12 tests of `tests/test_dashboard_classify.py`
  plus `ClassifyTxTypeMatrixTests` and `EffectiveCreditLimitTests` from `tests/test_dashboard_helpers.py`
  go to `tests/test_enrichment.py`. `LabelSubtypeTests` goes to `tests/test_api_viewmodels.py`. Run the full
  suite: the test count must be unchanged.

### 55b — Delete Streamlit (checkpoint B)

- Delete `app/` (`auth.py`, `dashboard.py`, `streamlit_app.py`, `static/mobile.css`, `__init__.py`) and the
  root `streamlit_app.py`.
- Delete `tests/test_app_auth.py` (10 Streamlit sign-in tests), and `tests/test_dashboard_helpers.py` /
  `tests/test_dashboard_classify.py` once 55a has moved their cases (`MobileStylesheetTests` goes with
  `mobile.css`).
- Delete `DatabaseClient.get_budgets` / `upsert_budget` (`database/db.py:502`, `:511`). Only Streamlit calls
  them; check with `git grep` and update `tests/test_db_upserts.py`. **Keep the `budgets` table** (item 3).
- In `requirements.txt`, drop `streamlit` and `plotly` (only `app/dashboard.py` and its test import plotly).
  Regenerate `requirements.lock` with hashes using the Phase 1f procedure (archive).
- In `core/config.py`, drop the `.streamlit/secrets.toml` layer, so precedence becomes environment → `.env` →
  default. Update the `ConfigError` text, `tests/test_config.py`, the docstrings in `api/deps.py` and
  `scripts/plaid_link.py`, and the `.gitignore` entry. The main checkout has no `.streamlit/secrets.toml`
  (existence checked 2026-10-20, contents never read).
- Rewrite the "port of `_build_sidebar_filters`" framing in `api/filters.py`'s docstring: it is now the
  source of truth. Its three invariants and `tests/test_api_filters.py` stay as they are. Do the same for the
  "frozen"/"port of" wording in `api/viewmodels.py`, `api/dataload.py`, `pipeline/runner.py` and the
  `web/src` comments (`BudgetTab.tsx`, `lib/filters.ts`, `lib/strings.ts`).

### 55c — Docs (checkpoint C)

- **`docs/deployment.md`:** replace the Streamlit "Dashboard" section with the real deployment:
  - Vercel serves `web/`, and `web/vercel.json` rewrites `/api/*` to the Render service.
  - Render runs `uvicorn api.main:app` with `DATABASE_URL`, the `GOOGLE_OAUTH_*` variables,
    `GOOGLE_ALLOWED_EMAILS` and `FRONTEND_ORIGIN`.
  - The Google redirect URI is the API's callback. Verify the exact path against `api/routers/auth.py` before
    writing it down.
- **`docs/setup-google-oauth.md`:** drop the `http://localhost:8501/` and Streamlit Community Cloud redirect
  URIs.
- **`README.md`:** architecture, quickstart (no `streamlit run`), configuration order, and the screenshot
  captions (pairs with O1).
- **`CONTRIBUTING.md` and `CLAUDE.md`:**
  - the `app/` bullet, the freeze notes, and the `streamlit run` command;
  - the paragraph saying `viewmodels.py` reuses `app/dashboard.py`'s helpers;
  - `filters.py` described as a port;
  - configuration precedence;
  - `budgets` as Streamlit-owned (now: legacy, inert, kept for 026's seed);
  - `is_outlier` described as a Streamlit shim (now: the anomaly-row flag the React filter reads).
- **ADR 0013 "Decommission Streamlit":** short. It supersedes the Phase 15 freeze and records why `budgets`
  and `is_outlier` survive. Add status notes to ADR 0005 (`budgets` ownership) and ADR 0007 (the shim
  wording), and update ADR 0010 / ADR 0012's references to `_classify_tx_type` /
  `_detect_internal_transfers` to their new names.

### 55d — Owner actions (no code)

- Delete the app on Streamlit Community Cloud, together with its secrets.
- Remove the Streamlit Community Cloud URL and `http://localhost:8501/` from the Google OAuth client's
  authorized redirect URIs.

### Verification

1. After 55a: `python -m unittest discover -s tests -v` is green with the **same test count** as before.
2. After 55b: `git grep -n "from app\."` returns nothing. `git grep -n -i streamlit -- ':!docs/plan-archive.md'
   ':!docs/research/' ':!docs/adr/' ':!PLAN.md'` returns nothing.
3. In a fresh venv, `pip install -r requirements.txt` installs neither `streamlit` nor `plotly`, and
   `pip install --require-hashes -r requirements.lock` succeeds.
4. `tests/test_migrations_execute.py` against `MIGRATION_TEST_DATABASE_URL` shows `ensure_schema()` still runs
   clean with `budgets` in place.
5. A pipeline run on a disposable database (as in O6) succeeds, and the anomaly rows still get `is_outlier`
   set. The React outliers-only filter still returns them.
6. The four web checks are green. Sign-in on the deployed Vercel + Render dashboard works for both
   allowlisted accounts, desktop and mobile.

---

## Phase 37-54 — Budget tab: a complete budgeting toolkit and generic Plans

> **Status:** designed, not yet implemented. Produced by a `/grill-with-docs` session (2026-10-20) over
> `docs/research/budget-tab-best-practices.md`. **This work targets `dev`, not `main`.** Four ADRs record
> the decisions that are hard to reverse: **0009** (Plans as base + layers, closed amount forms, one
> projection engine), **0010** (sinking funds measured by balance; tracking budget reaffirmed), **0011**
> (two-level Subcategories with slack) and **0012** (Account holder and shared-cost settlement). Every
> new term is in `CONTEXT.md`.
>
> **Guiding rule from the user:** every feature is generic and "applicable to any scenario". Nothing
> encodes the user's own spreadsheet. Their situation (two members, a wedding, a property purchase,
> tuition paid per session) is a test case each feature must be able to express. It is not the spec.
>
> Phases are commit-sized and follow the checkpoint workflow: each stops uncommitted, with a recommended
> commit title and body for the user to commit.
>
> **Prerequisite: Phase 55** (decommission Streamlit), above. The code paths below assume its new homes:
> `database/frames.py::load_financial_data` and `analytics/enrichment.py` (`classify_tx_type`,
> `detect_internal_transfers`, `enrich_transactions`).

### Why this work

Phases 28-35 gave the Budget tab per-month caps, goals, a forecast and anomalies. It is still a scorecard
plus a short forecast. The research found three gaps:

1. **The monthly instrument lacks the standard toolkit.** It has no totals or "remaining", can't show how
   far over a cap is, has no subcategory caps, no sinking funds, no separation of regular income from
   windfalls, no splits, and no alerts.
2. **Forward planning lives in a spreadsheet.** No surveyed tool models lines that grow, lock for a term or
   end on a date, and only one (Monarch, on a paid tier) offers scenarios side by side.
3. **Nothing exports a shareable budget with its assumptions.** Every tool's export is a transaction dump
   or a backup.

### Decisions locked

| Question | Decision |
|---|---|
| Scope | The full monthly toolkit **and** generic Plans, so the spreadsheet can be retired. |
| Philosophy | Tracking budget. **No rollover, no envelopes** (ADR 0010 reaffirms ADR 0005). |
| Sinking funds | Amount + cadence + next due date, held in a nominated Account. Measured as **Required balance vs actual balance**; never a stored balance. |
| Saved this month | Net balance growth of the Accounts nominated by goals and funds. Card payments and internal transfers stay transfers; `classify_tx_type` / `detect_internal_transfers` are not weakened. |
| Hierarchy | Exactly two levels. A curated, closed Subcategory set per Category. A Category's cap is the sum of its children or larger (the difference is Unallocated slack); a cap below the sum shows a **warning, not a block**. |
| Subcategory assignment | Per-transaction correction > merchant pin > Plaid-detail claim (**only** when the claiming Subcategory's parent is the transaction's effective Category) > none (counts against slack). |
| Subcategory caps | ADR 0005 inheritance, stored in a **sibling table** (see Constraints 1). |
| Household | One household budget. **Configurable** Household members (never hardcoded "me/partner"). Per-person **views** only: caps, plans and goals stay household-level. |
| Attribution | Account holder (a member, or Joint), set by the user once per Account. `owner_name` is never used for attribution. |
| Shared spending | Joint Accounts + Categories marked shared (wherever paid) ± a per-transaction override. |
| Fair share | Share basis: presets (equal, proportional to Regular income) or a custom ratio. Transfers between members settle; transfers into a Joint Account are contributions. |
| Regular income | Inflow Recurring streams, net as deposited, with a per-stream override. The basis for "remaining" and every ratio. |
| Expected income | Declared (amount, expected month or cadence, member). **Never** counted in "remaining" before it arrives. A deposit is **suggested** as its match and the user confirms. |
| Windfall allocation | Allocation rules produce one-click suggestions; they never move money. |
| Line class | Fixed / Essential / Flexible / Savings. **A label only**: behaviour lives in the line's own fields. Shared by Categories, Subcategories and plan lines. Defaults come from code, so there is no seed. |
| Ratios | User-defined (Categories, Subcategories and plan lines ÷ Regular income) with an optional user-set threshold. **No built-in 30% rule.** |
| Excluded categories | Still recorded, but never counted in totals, caps or ratios. |
| Pending | Counts against caps, always shown as "incl. $X pending". |
| Budget period | Calendar months only. ADR 0005 is unchanged. |
| Windowed caps | A Category's cap is monthly **or** windowed (a calendar year, or N months from a start), never both. Judged against an even pace; windows inherit window to window. |
| Splits | Parts always sum to the whole, and budgets count the parts. When Plaid revises the amount, parts are **rescaled proportionally and flagged for review**. |
| Tags | A closed list, applied in the ledger, in bulk, or by rule (merchant × date window). |
| Manual transactions | Manual Accounts (`source = 'manual'`), fully editable; sync and reconciliation never touch them. |
| Plan kinds | Full plan and Event plan. A projection is one base (the Actual baseline or one Full plan) + any number of Event plans. |
| Plan states | Draft (explore only) / Active (≤1 Full plan + any number of Event plans; drives cap suggestions and plan-vs-actual) / Archived. |
| Inputs | Household assumptions (inflation, income growth) + per-plan inputs. |
| Amount forms | A closed set: number, input, % of input, per-occurrence × count, Amortizing loan. Every line renders as a sentence. **No free-form formulas**; the XLSX export is the escape hatch. |
| Amortizing loan | Generic for any loan: fixed payment for a term, re-amortized at a renewal-rate input at term end; exposes the remaining principal. |
| Frequency | Monthly / every N months from a start / on listed months / once / spread evenly over a window. Optional start and end month (both inclusive). |
| Growth | Annual steps on plan-year boundaries (months 13, 25, ...), on amounts in plan-start dollars. The rate is a number or an input. |
| Scenarios | Belong to one plan; override its inputs and the household assumptions; compared in N columns side by side. A scenario never adds or removes lines. |
| Projection | Monthly engine, yearly view with drill-down to months. Horizon 1-10 years, default 5. |
| Engine | **One** engine. The Phase 32 forecast is re-expressed on it, and `tests/test_forecast.py` passes unchanged. |
| Plan → caps | The tab suggests and the user adopts per Category, which writes an explicit cap. **Never** auto-seeded. |
| Plan actuals | Recurring lines link to a Category or Subcategory; one-time lines track a Tag. |
| Plan ↔ goals | A line can link to a Savings goal or Sinking fund; activating a plan *offers* to create any that are missing. |
| Extra features in scope | Splits, windowed caps, safe-to-spend + alerts, rebalance, templates, unassigned-income check, 12-month grid, bill calendar + snooze, subscription review, manual accounts, reimbursables, settlement, emergency-fund target (N months of Fixed + Essential), excluded categories, allocation rules, setup wizard, debt payoff planner, projected liquidity line, XLSX export, configurable currency, plan versioning + review flags. |
| Out of scope | Net-worth projection, real-vs-nominal toggle, CSV export, payday-aligned periods, envelope rollover, XLSX re-import, free-form formulas, Quebec/Canada-specific rules. |
| Alerts delivery | In-app, plus an **SMTP** email digest that is off when unset. The digest carries category-level headlines and **never** account names, masks, merchants or descriptions. It is blocked until the scheduled pipeline is live. |
| Debts | Ingested credit and loan Accounts + manual debts. APR and minimum payment are entered by hand. Avalanche or snowball order. |
| Streamlit | Decommissioned by Phase 55, which lands first. `budgets` stays as an inert legacy table (Phase 55, item 3), and new state goes in new tables. |

### Constraints discovered during grilling

1. **`budget_periods` can't take a nullable `subcategory` column.** Postgres treats NULLs as distinct under
   `UNIQUE`, so `UNIQUE (category, subcategory, period)` would allow two parent rows for one month. Child
   caps go in a sibling table, `subcategory_budget_periods` (ADR 0011).
2. **`pending` is not in the cached frames.** `load_financial_data` never selects it. Once Phase 55 has moved
   the loader to `database/frames.py`, add `t.pending` to its SELECT directly; there's no need for another
   `api/dataload.py` merge (`api/dataload.py:63` exists only because the loader was frozen).
3. **The currency is hardcoded as `'USD'` in nine web files:** `BudgetTab.tsx`, `CashFlowTab.tsx`,
   `ForecastChart.tsx`, `GoalsSection.tsx`, `MetricTile.tsx`, `NetWorthTrendChart.tsx`, `OverviewTab.tsx`,
   `PeriodTransactionsPreview.tsx` and `TransactionsTab.tsx`. Each has its own local formatter.
4. **`merge_account` (`database/db.py:448`) already carries `manual_credit_limit`** onto the canonical row.
   Account holder needs the same treatment, plus every new `account_key` reference (sinking funds, debts).
   The `accounts` upsert must never name the holder columns.
5. **Rows deleted by `merge_account` or `reconcile_transactions` would cascade away user annotations**
   (tags, splits, reimbursable marks, shared overrides, subcategory corrections). Both methods must re-point
   annotations onto the surviving row of the same natural key before deleting, through one helper. The
   reconcile guard itself is load-bearing and is not relaxed. Test this in `tests/test_db_roundtrip.py`.
6. **Manual transactions would collide on `transaction_hash`.** Without a `transaction_id`,
   `build_transaction_hash` falls back to `account_key|date|description|amount`, so two genuine repeat cash
   purchases would collide on the UNIQUE. Manual rows carry a generated `MANUAL-<uuid4>` id so they hash
   per entry.
7. **`build_budget` caps `pct` at 1.0** (`api/viewmodels.py`, `min(spent / limit, 1.0)`), so "112% of cap"
   is not representable today.
8. **Regular income is derivable as-is.** `recurring_streams.direction` already distinguishes `inflow` from
   `outflow` (migration 027); only `upcoming_from_streams` filters to outflows.
9. **`forecast.project` already takes `max_horizon_months`**, so the 36-month Budget-tab ceiling and the
   120-month Plans ceiling can share an engine without a module-constant change.
10. **`ensure_schema()` re-runs every `.sql` on every call.** All new DDL uses `IF NOT EXISTS` /
    `ADD COLUMN IF NOT EXISTS`. Any data seed is guarded on a `schema_seeds` row. Default line classes come
    from code, so no seed is needed.
11. **SQL is only verified against a real Postgres** by `tests/test_migrations_execute.py` and
    `tests/test_db_roundtrip.py`. Every new statement is added to one of them, and columns are named
    `transaction_date`, never `date` (CLAUDE.md, migration 026's outage).
12. **Dependency-driven reorder:** Expected income needs a member, so Household members and Account holder
    move up into Phase 40. Settlement stays in Phase 47.
13. **Every write endpoint calls `dataload.invalidate(db.database_url)`**, and `web/src/lib/types.ts` changes
    in the same commit as the Pydantic models (`tests/test_api_dataload.py` enforces the first rule).
14. **Read-time derivation over stored derivation** wherever the input can change retroactively:
    effective Subcategory, rule-applied Tags, split explosion, Required balance and settlement balances
    are computed when frames are built, never persisted. This follows the "computed, never stored" reasoning
    of ADR 0010, so a changed claim, rule or basis applies to history without a pipeline re-run.

### Phase 37 — Budget quick wins: totals, over-by, pending, currency, notes, exclusions

- **Migration `030_category_settings.sql`:** `category_settings (category TEXT PRIMARY KEY, is_excluded
  BOOLEAN NOT NULL DEFAULT FALSE, note TEXT, source_url TEXT, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`.
  `category` is validated by `canonicalize()` in the API. No seed: an absent row means defaults.
- **Config:** `CURRENCY` (ISO 4217, default `USD`) and `NUMBER_LOCALE` (BCP 47, default `en-US`), in
  `Settings` / `load_settings()` and `.env.example`. A new `GET /settings` returns `{currency, locale}`.
  `web/src/lib/money.ts` becomes the single formatter, replacing the nine local ones (Constraint 3).
- **`build_budget`:**
  - `pct` is uncapped, plus a new `over_by` field (`max(spent − limit, 0)`, or `null` with no cap).
  - `pending_spent` per item, from the loader's new `pending` column (Constraint 2).
  - Excluded Categories leave `items` and totals and are returned in a separate `excluded` list.
  - A new `totals {budgeted, spent, pending, remaining_vs_caps}`. Regular income joins the totals in Phase 40.
- **API:** `PUT /category-settings/{category}` (note, source_url, is_excluded). Invalidates dataload.
- **UI:**
  - A totals header.
  - "+$84 (112%)" on over-budget rows, with the bar capped visually and an overflow marker.
  - "incl. $X pending" on rows that have pending spend.
  - A note popover with the source link opening in a new tab (`rel="noopener noreferrer"`).
  - A collapsed "Excluded" group with a toggle per row.
- **Tests:**
  - `test_api_viewmodels`: pct 1.12, `over_by`, a zero cap with spend, excluded never in totals, pending
    subtotal.
  - `test_config`: currency/locale defaults and env override.
  - `money.test.ts`; `BudgetTab.test.tsx` for the header and the over-by label.

### Phase 38 — Line classes, Ratios, and the 50/30/20 reference

- **Migration `031_line_classes_and_ratios.sql`:**
  - `ALTER TABLE category_settings ADD COLUMN IF NOT EXISTS line_class TEXT CHECK (line_class IN
    ('fixed','essential','flexible','savings'))`.
  - `ratios (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, threshold NUMERIC(6,4) NULL, direction
    TEXT NOT NULL CHECK (direction IN ('at_most','at_least')), note TEXT)`.
  - `ratio_terms (id BIGSERIAL PRIMARY KEY, ratio_id BIGINT NOT NULL REFERENCES ratios ON DELETE CASCADE,
    category TEXT NOT NULL)`. Subcategory and plan-line terms are added in Phases 39 and 44.
- **`analytics/categories.py::DEFAULT_LINE_CLASS`** maps every canonical name to a class (e.g.
  `LOAN_PAYMENTS` → fixed, `FOOD_AND_DRINK` → flexible, `MEDICAL` → essential). The effective class is the
  stored override, else this default.
- **`analytics/ratios.py` (pure):** `evaluate(ratio, spend_by_key, regular_income)` → `{value, threshold,
  breached, basis}`. Regular income is `None` until Phase 40, so the ratio reports "no income basis yet"
  and never divides by spend.
- **50/30/20 reference:** Fixed + Essential vs needs, Flexible vs wants, Savings vs savings. It is displayed
  as a *reference* beside real shares and never enforced.
- **UI:** class subtotal rows on the Budget tab, a class picker per row, and a Ratios panel with a
  create/edit dialog. Examples are offered as editable starting points, never pre-created.
- **Tests:** `test_ratios.py` (threshold directions, no income, Excluded categories never counted), class
  defaults covering every canonical name (a test fails when a new canonical name lacks a default).

### Phase 39 — Subcategories (ADR 0011)

- **Migration `032_subcategories.sql`:**
  - `subcategories (id BIGSERIAL PRIMARY KEY, category TEXT NOT NULL, name TEXT NOT NULL, line_class TEXT
    NULL, note TEXT, UNIQUE (category, name))`.
  - `subcategory_detail_claims (pfc_detailed TEXT PRIMARY KEY, subcategory_id BIGINT NOT NULL REFERENCES
    subcategories ON DELETE RESTRICT)`. Each detail value is claimed by at most one Subcategory.
  - `subcategory_budget_periods (subcategory_id BIGINT NOT NULL REFERENCES subcategories ON DELETE
    RESTRICT, period TEXT NOT NULL, monthly_limit NUMERIC(12,2) NOT NULL, UNIQUE (subcategory_id, period))`.
  - `ALTER TABLE merchant_categories ADD COLUMN IF NOT EXISTS subcategory_id BIGINT NULL REFERENCES
    subcategories`.
  - `ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_subcategory_id BIGINT NULL REFERENCES
    subcategories`. **Never named by `upsert_transactions`.**
  - `ALTER TABLE ratio_terms ADD COLUMN IF NOT EXISTS subcategory_id BIGINT NULL REFERENCES subcategories`.
- **`analytics/subcategories.py` (pure):**
  - `resolve_subcategory(effective_category, pfc_detailed, merchant_pin, user_subcategory, subcats)`
    applies the precedence in the Decisions table. A pin or correction whose parent is not the effective
    Category is ignored, so the Category correction wins.
  - `slack(category_cap, child_caps, unassigned_spend)` returns slack and a `cap_below_children` flag.
    Applied at read time in `api/dataload.py` (Constraint 14).
- **Caps:** `resolve_caps_detailed` is reused unchanged for child rows, keyed on `subcategory_id`.
- **`build_budget` items gain:**
  - `subcategories: [{id, name, spent, pending, limit, pct, over_by, is_inherited, inherited_from}]`;
  - `slack {limit, spent}`, `children_sum`, `cap_below_children`;
  - `suggestions`: unclaimed `pfc_detailed` values with spend this month, so the UI can offer "Create a
    Subcategory for $180 of GAS_AND_ELECTRICITY?".
- **API:**
  - `GET/POST/PATCH/DELETE /subcategories`. DELETE returns **409 with counts** while caps, pins, claims or
    corrections reference the Subcategory.
  - `PUT/DELETE /subcategory-budgets/{id}?month=`, and `PUT /subcategory-claims/{pfc_detailed}`.
  - `update_transaction_category` takes an optional `subcategory_id` (validated against the parent), and
    merchant memory upserts it alongside the Category.
- **UI:** the expanded row lists children with inline cap editing, a slack row, the below-sum warning and the
  suggestion chips. The ledger gets a Subcategory column and correction picker.
- **Tests:** `test_subcategories.py` (precedence, the parent guard, slack arithmetic, the below-sum warning,
  inheritance through `resolve_caps_detailed`). SQL goes in `test_db_roundtrip.py`.

### Phase 40 — Household members, Account holder, and income

- **Migration `033_household_and_income.sql`:**
  - `household_members (id BIGSERIAL PRIMARY KEY, display_name TEXT NOT NULL UNIQUE, created_at)`.
  - `ALTER TABLE accounts ADD COLUMN IF NOT EXISTS holder_kind TEXT NULL CHECK (holder_kind IN
    ('member','joint')), ADD COLUMN IF NOT EXISTS holder_member_id BIGINT NULL REFERENCES
    household_members`, plus a CHECK that `holder_member_id` is set iff `holder_kind = 'member'`.
  - `stream_income_overrides (stream_id TEXT PRIMARY KEY, is_regular BOOLEAN NOT NULL)`. **First verify that
    `stream_id` is stable across `derive_streams` re-runs**; if it isn't, key on `merchant_key`.
  - `expected_income (id, label, member_id NULL, amount NUMERIC(12,2), cadence TEXT CHECK (cadence IN
    ('once','every_n_months')), every_n_months INT NULL, expected_period TEXT, window_months INT NOT NULL
    DEFAULT 1, note, is_active BOOLEAN)`.
  - `expected_income_matches (expected_income_id, period, transaction_hash UNIQUE REFERENCES transactions,
    confirmed_at)`.
  - `allocation_rules (id, name UNIQUE, is_default BOOLEAN)` and `allocation_rule_parts (rule_id,
    target_kind CHECK (target_kind IN ('goal','sinking_fund','debt','free')), target_id NULL, share NUMERIC(5,4))`.
    Shares must sum to 1, validated in the API.
- **Holder survives the pipeline:** the `accounts` upsert never names `holder_*`, and `merge_account` carries
  them onto the canonical row when it has none (Constraint 4).
- **`analytics/income.py` (pure):**
  - `classify_income(frame, streams, overrides)` → regular / other.
  - `match_candidates(expected, deposits)`: within the expected window ±1 month, amount ±25%, on Accounts
    held by the declared member (or Joint).
  - `allocate(amount, rule)` → suggestions.
- **`build_budget` totals add:**
  - `regular_income` and `remaining = regular_income − spent`;
  - `unassigned_income = regular_income − Σ caps`, which becomes `− Σ Savings set-asides` once Phase 42
    lands;
  - a `windfalls` block: non-regular income received this month plus Expected-income match status.
- **Per-person views:** a Holder multi-select (members, Joint, Unassigned) in the filter bar.
  `api/filters.py` (the source of truth since Phase 55) gains a holder filter, pinned in
  `tests/test_api_filters.py`.
- **API:** `/members` CRUD; `PATCH /accounts/{key}/holder`; `/expected-income` CRUD +
  `POST /expected-income/{id}/match`; `/allocation-rules` CRUD; `PUT /income-streams/{id}/override`.
- **UI:** a Settings panel for members and holders; income and remaining in the totals header; an Expected
  income block; a match-suggestion banner; allocation suggestions after a confirmed match.
- **Tests:** `test_income.py` (classification, match window and tolerance, allocation sums), `merge_account`
  carrying the holder (roundtrip), and the filter extension.

### Phase 41 — Tags

- **Migration `034_tags.sql`:**
  - `tags (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, is_archived BOOLEAN NOT NULL DEFAULT FALSE)` with a
    unique index on `lower(name)`.
  - `transaction_tags (transaction_hash TEXT REFERENCES transactions ON DELETE CASCADE, tag_id BIGINT
    REFERENCES tags, state TEXT NOT NULL CHECK (state IN ('on','off')), PRIMARY KEY (transaction_hash,
    tag_id))`. An `off` row suppresses a rule match for that one transaction.
  - `tag_rules (id, tag_id, merchant_key TEXT NOT NULL, start_date DATE NULL, end_date DATE NULL)`.
- **`analytics/tags.py` (pure):** effective tags = explicit `on` ∪ rule matches − explicit `off`. Applied at
  read time (Constraint 14).
- **Annotation re-pointing (Constraint 5):** add `DatabaseClient._move_annotations(from_hash, to_hash)`,
  called by `merge_account` and `reconcile_transactions` before deleting. Later phases extend it to
  splits, reimbursables, shared overrides and subcategory corrections.
- **API:** `/tags` CRUD (archive, never delete while referenced), `PUT /transactions/{hash}/tags`,
  `POST /transactions/tags:bulk`, `/tag-rules` CRUD.
- **UI:** tag chips in the ledger, bulk tagging from a selection, a tag filter, and a rules editor. No
  emojis, and no free-text tag creation inline (you pick from the list or create one explicitly).
- **Tests:** `test_tags.py` (union/suppression, date-window bounds inclusive), annotation re-pointing in
  `test_db_roundtrip.py` for both merge and reconcile.

### Phase 42 — Sinking funds, Saved this month, emergency-fund target (ADR 0010)

- **Migration `035_sinking_funds.sql`:**
  - `sinking_funds (id, name, amount NUMERIC(12,2), cadence_months INT CHECK (cadence_months > 0),
    next_due_date DATE, account_key TEXT REFERENCES accounts, category NULL, subcategory_id NULL, note,
    is_active)`.
  - `ALTER TABLE savings_goals ADD COLUMN IF NOT EXISTS target_kind TEXT NOT NULL DEFAULT 'amount' CHECK
    (target_kind IN ('amount','months_of_essentials')), ADD COLUMN IF NOT EXISTS target_months NUMERIC NULL`.
  - `merge_account` re-points `sinking_funds.account_key`. While there, **verify `savings_goal_accounts` is
    re-pointed too**, and fix it if not.
- **`analytics/sinking_funds.py` (pure):**
  - `current_cycle(fund, today)` advances `next_due_date` by cadence until it is ≥ today. This is computed:
    the payout transaction is not needed.
  - `accrued(fund, today) = amount × months_elapsed_in_cycle / cadence_months`.
  - `required_balance(funds, today)` per Account; `funded_ratio(actual, required)`.
  - `monthly_set_aside(fund) = amount / cadence_months`.
  - `is_spent_from(account, frame)` flags an Account with regular expense activity, where the comparison is
    not meaningful (ADR 0010, Consequences).
- **`analytics/goals.py::saved_in_period(nominated_accounts, snapshots, period)`:** Σ (end − start balance)
  over the **distinct** nominated Accounts (an Account shared by two goals counts once). Returns `None`
  with a reason when snapshots don't cover the period, and always states its basis.
- **Emergency-fund target:** a goal with `target_kind = 'months_of_essentials'` resolves its target as
  `target_months × trailing median monthly (Fixed + Essential) spend`, with a 3-complete-month minimum,
  recomputed at read time and labelled.
- **Savings class in the budget:**
  - Planned = each goal's needed monthly (remaining ÷ months to target date) + each fund's set-aside.
  - Actual = Saved this month, at class level only, because balance growth can't be attributed to one fund.
  - `unassigned_income` now subtracts Savings planned.
- **API:** `/sinking-funds` CRUD; `GET /sinking-funds/status` (per Account: required, actual, ratio,
  per-fund derived order).
- **UI:** a Sinking funds section beside Goals; a per-Account funded card; Savings class rows in the budget.
- **Tests:** `test_sinking_funds.py` (cycle advance across year ends, accrual at 0 and 100%, several funds per
  Account, the spent-from caveat), `saved_in_period` dedupe and missing snapshots, the months-of-essentials
  target.

### Phase 43 — One projection engine (ADR 0009)

- **`analytics/amortization.py` (pure):** `payment(principal, annual_rate, amort_months)`, with zero-rate
  handled. `schedule(principal, rate, amort_months, term_months, renewal_rate)` re-amortizes the remaining
  principal at the term end and returns monthly payment and remaining principal. Shared with Phase 51.
- **`analytics/projection.py` (pure):**
  - Typed `Line` (amount form, frequency, start/end, growth, direction, class, links, `effect`) and
    `Projection` objects.
  - `evaluate_amount(form, inputs)` over the closed union.
  - `occurrences(frequency, start, end, period)` for the five forms. The spread form divides evenly and puts
    the cents remainder in the last month.
  - `grown(amount, rate, months_since_plan_start)` steps at months 13, 25, ...
  - `project(base, layers, assumptions, scenario_overrides, start_period, horizon_months,
    max_horizon_months)` → monthly rows per line, per class, income, remaining, and cumulative remaining.
  - An Event-plan line's `effect` is `add` or `replace`. `replace` overrides the base's amount for its linked
    Category or Subcategory from its start month, which is how "rent stops" or "this payment replaces that
    one" is expressed generically.
  - Money is `Decimal` throughout and rounded half-even to cents only at output.
- **Actual baseline:** `actual_baseline(frame, streams, caps, today)` carries Phase 32's rules verbatim
  (streams on predicted dates, trailing medians, current month excluded, 3-month minimum).
  `analytics/forecast.py::project` becomes a thin adapter with the **same signature and return shape**, and
  `tests/test_forecast.py` passes unchanged. The Budget tab is visually unchanged in this phase.
- **Tests:**
  - `test_amortization.py`: standard-formula reference values, the zero rate, renewal re-amortization,
    term = amortization.
  - `test_projection.py`: each frequency form, growth at month 13 not 12, inclusive start/end, the spread
    remainder, base + two layers summing, `replace` vs `add`, scenario overriding an input and an assumption,
    the horizon ceiling refusing with a reason.

### Phase 44 — Plans: data model and API

- **Migration `036_plans.sql`:**
  - `household_assumptions (key TEXT PRIMARY KEY, value NUMERIC, unit TEXT, note TEXT, source_url TEXT)`.
  - `plans (id, name UNIQUE, kind CHECK (kind IN ('full','event')), status CHECK (status IN
    ('draft','active','archived')), start_period TEXT, horizon_years INT CHECK (horizon_years BETWEEN 1 AND
    10), note, reviewed_at TIMESTAMPTZ, review_every_months INT NOT NULL DEFAULT 6, duplicated_from BIGINT
    NULL REFERENCES plans, created_at, updated_at)`.
  - A partial unique index **`ON plans (kind) WHERE status = 'active' AND kind = 'full'`** (at most one active
    Full plan).
  - `plan_inputs (plan_id REFERENCES plans ON DELETE CASCADE, key, value NUMERIC, unit, note, source_url,
    UNIQUE (plan_id, key))`.
  - `plan_lines (id, plan_id, label, direction CHECK (direction IN ('expense','income')), line_class,
    effect CHECK (effect IN ('add','replace')), amount_form JSONB NOT NULL, frequency JSONB NOT NULL,
    start_period NULL, end_period NULL, growth JSONB NULL, category NULL, subcategory_id NULL, tag_id NULL,
    goal_id NULL, sinking_fund_id NULL, member_id NULL, note, source_url, sort_order INT)`.
  - `plan_scenarios (id, plan_id, name, overrides JSONB NOT NULL, UNIQUE (plan_id, name))`.
  - `plan_versions (id, plan_id, label, snapshot JSONB NOT NULL, created_at)`.
  - `ALTER TABLE ratio_terms ADD COLUMN IF NOT EXISTS plan_line_id BIGINT NULL REFERENCES plan_lines ON
    DELETE CASCADE`.
- **Validation:** `amount_form`, `frequency`, `growth` and `overrides` are Pydantic **discriminated unions**
  in `api/`; unknown kinds return 422. An input referenced by a line must exist on the plan or be a
  household assumption. `replace` lines need a Category or Subcategory link, and are only allowed on Event
  plans.
- **API:**
  - `/plans` CRUD, `POST /plans/{id}/duplicate`, `POST /plans/{id}/versions`, `GET /plans/{id}/versions`.
  - `POST /plans/{id}/status`: activating a second Full plan returns 409 naming the active one.
  - `/household-assumptions` CRUD; `/plans/{id}/scenarios` CRUD.
  - `GET /projection?base=actual|plan:{id}&layers=..&scenario=..&horizon_years=..`.
- **Tests:** API validation per form, one-active-Full enforced in the DB and the API, versions snapshot
  round-trip, SQL in `test_db_roundtrip.py`.

### Phase 45 — Plans UI

- **Placement:** the Budget tab gains a "Month | Plans" segmented control, so Plans stay inside the primary
  tab (the same reasoning ADR 0008 gives for Goals).
- **Plan list:** kind, status, last reviewed, and a review-due flag; duplicate, archive, versions.
- **Editor:**
  - An inputs table with notes and source links.
  - Lines rendered as their **sentences** with a form-specific editor.
  - Household assumptions in a shared panel, marked as affecting every plan.
- **Projection view:**
  - A base picker (Actual baseline or a Full plan), layer checkboxes (drafts included), and a scenario
    picker.
  - A yearly table by class with income, remaining, ratios and the multi-year total; any year drills down
    to months.
- **Scenario comparison:** N columns. Rows are monthly cost by class (year 1), total monthly, remaining,
  each ratio, cash needed (one-time lines in the window) and minimum liquidity.
- **Projected liquidity line:**
  - Starts from the balance of chosen Accounts (default: depository only, the Phase 32 rule) and adds
    cumulative remaining minus one-time costs.
  - A floor input defaults to the emergency-fund goal's target when one exists; months below the floor are
    highlighted.
- **Tests:** sentence rendering for every form, layer toggling, scenario columns, liquidity highlight.

### Phase 46 — Plan ↔ budget

- **Plan-vs-actual on the Month view:**
  - Each line of an Active plan with a Category or Subcategory link shows planned vs actual for the
    displayed month.
  - One-time lines show cumulative tagged spend vs the line total.
  - Income lines are compared against Regular income per member.
- **Cap suggestions:** a row shows "plan $450 [adopt]" when an Active plan's linked amount differs from the
  resolved cap. Adopting writes an explicit cap through the existing ADR 0005 endpoint. Nothing is
  written automatically.
- **Activation offers (each a checkbox, nothing created silently):**
  - a Savings goal for a one-time line marked "funded by a goal";
  - a Sinking fund for every non-monthly line;
  - a Tag for every one-time line.
- **Forecast:** the Budget tab's forecast becomes `projection(actual baseline + Active Event plans)`, and
  `ForecastChart` names the plans layered in.
- **Review flags:** a plan past `review_every_months` raises a `plan_review_due` alert (Phase 50); "Mark
  reviewed" stamps `reviewed_at`.
- **Tests:** suggestion equality edge (no suggestion when equal), adopt writes exactly one explicit row,
  activation offers.

### Phase 47 — Shared-cost settlement (ADR 0012)

- **Migration `037_settlement.sql`:**
  - `ALTER TABLE category_settings ADD COLUMN IF NOT EXISTS is_shared BOOLEAN NOT NULL DEFAULT FALSE`.
  - `ALTER TABLE transactions ADD COLUMN IF NOT EXISTS shared_override BOOLEAN NULL`. **Never named by
    `upsert_transactions`**, and added to `_move_annotations`.
  - `household_settings (key TEXT PRIMARY KEY, value JSONB NOT NULL, updated_at)`, holding `share_basis`
    (`{kind: equal|income|custom, ratios}`) and `settlement_start` (`YYYY-MM`).
- **`analytics/settlement.py` (pure):**
  - Shared spending set, fair share per member by basis (income-proportional recomputed per period from
    Regular income).
  - Paid per member: own Account → that member; Joint Account → in proportion to contributions that period.
    With no contributions observed, it falls back to fair share and is flagged.
  - Member-to-member transfers settle (via the existing transfer pairing, read with holders).
  - The running balance is computed from `settlement_start` and never stored. Every figure states its basis.
- **UI:** a Household card on the Month view with fair share / paid / balance per member and a share-basis
  selector with the presets. Ledger rows get a shared on/off override.
- **Tests:** `test_settlement.py` (equal / income / custom, a personal card in a shared Category, a joint
  Account funded unevenly, settlement transfers, no-contribution fallback flagged).

### Phase 48 — Splits, reimbursables, manual accounts

- **Migration `038_splits_reimbursables_manual.sql`:**
  - `transaction_splits (id, transaction_hash REFERENCES transactions ON DELETE CASCADE, part_no INT, amount
    NUMERIC(12,2), category TEXT NOT NULL, subcategory_id NULL, needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    original_total NUMERIC(12,2) NOT NULL, UNIQUE (transaction_hash, part_no))`.
  - `transaction_split_tags (split_id, tag_id, PRIMARY KEY (split_id, tag_id))`.
  - `reimbursables (transaction_hash PRIMARY KEY REFERENCES transactions, status CHECK (status IN
    ('outstanding','settled','written_off')), matched_transaction_hash NULL, note)`.
- **Splits:**
  - `api/dataload.py` explodes a split transaction into its parts at read time; budgets count parts.
  - When the current amount ≠ `original_total`, parts are rescaled proportionally (the cents remainder goes
    to the largest part) and `needs_review` is set. Confirming stores the new `original_total`.
  - Splits are added to `_move_annotations`.
- **Reimbursables:**
  - An outstanding one is excluded from spend.
  - The matched repayment is excluded from income.
  - Written off returns it to spend.
- **Manual accounts:**
  - `accounts.source = 'manual'`, with `account_key` `manual:<uuid4>`.
  - Transactions get `external_id` `MANUAL-<uuid4>` passed as the transaction id (Constraint 6).
  - The balance is set by hand as an `account_balance_snapshots` row.
  - Ingestion account-claiming, `reconcile_transactions` and `delete_transactions_by_external_ids` all
    **explicitly exclude `source = 'manual'`**, each with a test. `purge_sample_data.py` only touches
    `'sample'` and is unaffected.
- **API:** `/transactions/{hash}/split` (PUT/DELETE, sum-equals-total validated), `/reimbursables`,
  `/manual-accounts` CRUD, `/manual-transactions` CRUD.
- **Tests:** the sum invariant, rescale and review flag, the reimbursable lifecycle, manual genuine repeats
  not colliding, sync/reconcile skipping manual rows.

### Phase 49 — Caps extended: windowed caps, templates, rebalance, snooze

- **Migration `039_cap_windows_and_snoozes.sql`:**
  - `ALTER TABLE budget_periods ADD COLUMN IF NOT EXISTS window_months INT NOT NULL DEFAULT 1 CHECK
    (window_months >= 1)`, and the same on `subcategory_budget_periods`. `monthly_limit` then holds the
    window's limit; the name is kept because renaming fights re-run migrations, and the docstring says so.
  - `cap_snoozes (scope_key TEXT NOT NULL, period TEXT NOT NULL, PRIMARY KEY (scope_key, period))`, where
    `scope_key` is `cat:<name>`, `sub:<id>` or `fund:<id>`.
- **Window resolution** (extend `analytics/budget_periods.py`):
  - An explicit row with window W at period P covers P..P+W−1.
  - Later windows inherit (same W and limit) until a later explicit row.
  - An explicit row inside a running window starts a new window there; a test pins this.
  - Judged by spent-to-date in the window vs pace = limit × elapsed fraction (day-level in the current
    month).
- **`analytics/templates.py` (pure):** caps from the average of the last N complete months, from 50/30/20 of
  Regular income split within each class by trailing spend, or from the Active plan. It returns a preview,
  and applying writes explicit caps for the chosen month in one transaction.
- **Rebalance:** `POST /budgets/rebalance {month, from, to, amount}` writes two explicit caps atomically,
  keeping the total unchanged.
- **Snooze:** a snoozed cap or fund is not judged for that month (no alerts, never "over") and is shown as
  snoozed.
- **Tests:** window resolution (inheritance, truncation, pace), template outputs, rebalance atomicity, snooze
  suppression.

### Phase 50 — Review surfaces: 12-month grid, bill calendar, subscriptions, safe-to-spend, alerts

- **Migration `040_reviews_and_alerts.sql`:** `stream_reviews (stream_id TEXT PRIMARY KEY, reviewed_at
  TIMESTAMPTZ, keep BOOLEAN)`; `alert_feedback (kind TEXT, subject TEXT, period TEXT, dismissed_at,
  PRIMARY KEY (kind, subject, period))`, which is period-scoped like `anomaly_feedback`.
- **12-month grid:** `GET /budget/grid?from=YYYY-MM&months=12` returns Categories × months of cap vs actual,
  plus a year-in-review (totals per class, months over cap, biggest variances).
- **Bill calendar:** outflow streams on predicted dates, Sinking-fund due dates and Regular-income dates
  (paydays) in one month view. It highlights days where cumulative bills exceed cumulative paydays.
- **Subscription review:** outflow streams with annualized cost (by cadence), last charge, a link to any
  price-creep anomaly, and a reviewed / keep marker.
- **Safe-to-spend:** current month only, per Category and for the Flexible class: (cap − spent − pending) ÷
  days remaining including today.
- **`analytics/alerts.py` (pure):**
  - Kinds: `cap_threshold` (user thresholds in `household_settings`, default 80% and 100%),
    `projected_overrun`, `fund_behind`, `goal_off_track`, `plan_review_due`, `expected_income_unmatched`
    (window passed) and `split_needs_review`.
  - Each alert carries its sentence. Snoozed scopes are skipped and dismissals are period-scoped.
- **UI:** an alerts strip on the Month view, row badges, and the grid, calendar and subscriptions as Month-view
  sections.
- **Tests:** `test_alerts.py` (each kind, snooze and dismissal scoping), the calendar shortfall, annualizing,
  safe-to-spend on the last day of the month.

### Phase 51 — Debt payoff planner

- **Migration `041_debts.sql`:** `debts (id, name, account_key NULL REFERENCES accounts, balance_manual
  NUMERIC NULL, apr NUMERIC(6,4) NOT NULL, min_payment NUMERIC(12,2) NOT NULL, is_included BOOLEAN NOT NULL
  DEFAULT TRUE)`. A linked debt reads its balance from the latest snapshot. `merge_account` re-points
  `account_key`.
- **`analytics/debt.py` (pure):**
  - Simulates avalanche (highest APR first) or snowball (smallest balance first) with an extra monthly
    amount and monthly interest at APR ÷ 12.
  - Returns the payoff month per debt, total interest, and interest saved vs minimums only.
  - Refuses, with the sentence why, when a minimum payment never covers its interest. Shares
    `analytics/amortization.py` helpers.
- **Extra payment source:** a Savings-class line named by the user (budget set-aside or plan line), never an
  implied surplus.
- **UI:** a Debts section with an order table, a payoff timeline chart (per `dataviz` guidance) and a
  strategy toggle.
- **Tests:** `test_debt.py` (both orders, rollover of a freed minimum into the next debt, the
  never-pays-off refusal, a zero-APR debt).

### Phase 52 — XLSX export

- **Dependency:** `XlsxWriter` (BSD-2-Clause), added to `requirements.txt` and `requirements.lock`.
- **`api/exports.py`** reuses the view models and `dataload` cache. Endpoints:
  - `GET /export/budget.xlsx?month=`, with sheets Summary (title, month, **generated-at**, currency,
    filters), Categories (class, Category, Subcategory, cap, spent, pending, over-by, %, note, source),
    Funds & goals, Expected income.
  - `GET /export/plans/{id}.xlsx`, with sheets Inputs (live cells, defined names, notes as cell comments,
    source URLs), Lines (each line's sentence plus its amount as a **formula with a cached value**:
    input refs, `%`, `×` count, and `PMT()` for loans), Projection (yearly by class, formulas over Lines
    where the form allows, otherwise values), Scenarios (one column each, values).
- **Privacy:** aggregates only. Never account names, masks, `account_key`, Plaid ids, `transaction_hash`
  or descriptions. Member names are allowed.
- **Sanitizer:** one function, `sanitize_text_cell`, implements OWASP (prefix `'` on a leading `= + - @`,
  tab, CR, LF and their full-width forms). Numbers are always typed numeric cells.
- **Web:** download buttons fetch with credentials and save the blob. Nothing goes in a URL.
- **Tests:** read the workbook back with stdlib `zipfile` + `xml.etree` (no new test dependency). Check
  that formulas carry cached values, the sanitizer cases, and the absence of sentinel account strings.

### Phase 53 — Email digest (blocked until the scheduled pipeline is live)

- **Config:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`
  (default true), `DIGEST_CADENCE` (`off|daily|weekly`, default `off`) and `DIGEST_WEEKDAY`, in `Settings`
  and `.env.example`. GitHub Secrets use the same names.
- **`analytics/digest.py` (pure):** alerts → headline sentences. A test seeds sentinel account names, masks,
  merchants and descriptions and asserts **none** appear in the output.
- **`core/mailer.py`:** an `smtplib` sender. Recipients are `GOOGLE_ALLOWED_EMAILS`. No other address is
  ever used.
- **`pipeline/runner.py`:** after a successful run, when the cadence is due, send it. Migration `042_digest.sql`
  adds `digest_log (period_key TEXT PRIMARY KEY, sent_at)`, so a manual dispatch plus the cron on the same
  day never double-sends, and `digest_status` / `digest_error_class` on `pipeline_runs`. **Nothing is printed
  to stdout** (the Actions log rule).
- **Tests:** cadence due/not due, idempotency per period key, failure recorded with the class only.

### Phase 54 — Setup wizard

- **First run** is detected when `household_members` is empty.
- **Steps:** members → Account holders → confirm Regular income streams → starter caps from a template
  (Phase 49) → an optional first goal or sinking fund → a read-only currency check (from config).
- Every step writes through existing endpoints, and each is skippable and resumable.
- **Tests:** step progression, resume after reload, skip leaving defaults.

### Documentation

- `CONTEXT.md`: terms added inline during the session.
- ADRs 0009-0012 written.
- **`CLAUDE.md` updates as phases land:**
  - migrations now 001-042;
  - the new upsert-never-names columns (`user_subcategory_id`, `shared_override`, `accounts.holder_*`);
  - `_move_annotations` in merge and reconcile;
  - the `source = 'manual'` exclusions;
  - the projection engine replacing the forecast's internals;
  - the new config keys.
- The README feature list.
- The research doc's status table (§6).

### Verification

Per phase, the named test file and its cases must exist and pass. Then run
`python -m unittest discover -s tests -v` and
`cd web && npm run test && npx tsc -b && npm run lint && npm run format:check`.
Then check live, on the user's own dashboard, in a git worktree so a running `uvicorn --reload` is never
restarted:

1. `python main.py` is clean, with one `pipeline_runs` row; caps, holders, tags, splits and overrides all
   survive a second run.
2. A cap at 112% reads "+$X (112%)"; pending shows separately; an Excluded category leaves the totals.
3. Changing `CURRENCY` re-formats every money value in all nine former formatter sites.
4. A Subcategory claiming a detail value picks up this month's spend. A merchant pin overrides it. A
   Category correction on the transaction beats both. The parent cap below the children's sum warns.
5. A joint Account shows under Joint; merging an Account fork keeps its holder.
6. Declare an expected bonus: it stays out of "remaining". A matching deposit is suggested, and confirming it
   shows the allocation suggestions.
7. Two sinking funds on one Account give the right Required balance; a chequing-backed fund shows the
   caveat.
8. The forecast chart is identical before and after Phase 43 for the same data; `test_forecast.py` is
   unchanged.
9. A Full plan + two Event plans project to the sum of their parts. A `replace` line stops a baseline
   Category from its month. A scenario changing an input re-prices every line using it.
10. Adopting a plan suggestion writes one explicit cap and leaves the previous month untouched.
11. Settlement: a personal-card purchase in a shared Category moves the balance by the other member's share.
12. Split a transaction, then simulate a revised amount: parts rescale and the review flag appears.
13. The exported XLSX opens in Excel: changing an input recalculates its lines, the cached values show in
    a viewer without a calculation engine, and the file contains no mask or account name.
14. The digest (once the pipeline is live) arrives once per period with headlines only.
