# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a Phase-1 build: the data path (ingest → process → persist → dashboard) is wired end-to-end first, ahead of
the full feature set described in the original design brief. What this means concretely:

- ML is stubbed — `pipeline/runner.py` uses `analytics/placeholders.py`, not the real `analytics/classifier.py` /
  `analytics/outlier_detector.py` yet (see Architecture).
- The dashboard implements all core views. Only ML is stubbed — the pipeline uses placeholders.
- Scheduled automation is not active yet — the GitHub Actions workflow is defined but does not run automatically (see
  Automation).

When extending, prefer wiring the existing real modules onto the live path over adding new parallel ones.

## Conventions

- **Decoupled from any specific user.** Never hardcode personal accounts, emails, tokens, or file paths. Every
  credential and tunable is read through `core/config.py` from env / `.env` / `.streamlit/secrets.toml` so any user can
  deploy with their own secrets. New config belongs in `Settings`/`load_settings()` and `.env.example`, not inline.
- **Lean, modular, single-responsibility.** Keep the layer boundaries strict (ingestion / database / analytics / app /
  core / pipeline) — a change in one layer should not reach into another. Match the existing concise style.
- **Ask, don't guess.** When a requirement or design decision is genuinely ambiguous, ask the user rather than making
  an uncertain assumption.
- **Never access, read, or print the `.env` file.** Do not open it, `cat`/`Get-Content` it, glob/grep into it, echo
  its contents, or include it in any tool output — even for debugging. It holds live secrets (DB URL, Plaid keys,
  OAuth secrets). If you need to confirm a variable is set, check `.env.example` for the key name or ask the user to
  confirm the value themselves; never read the real file to find out.

## Commands

- Install deps: `pip install -r requirements.txt` (requirements.txt is authoritative; pyproject.toml is minimal/incomplete)
- Run pipeline: `python main.py`
- Run the Streamlit dashboard (frozen reference implementation): `streamlit run streamlit_app.py`
- Run the API for the React dashboard: `uvicorn api.main:app --reload` (defaults to port 8000)
- Run the React dashboard: `cd web && npm run dev`. It needs the API running; point it at a
  non-default API with `VITE_API_URL`.
- Web checks (all four must pass): `cd web && npm run test && npx tsc -b && npm run lint && npm run format:check`
- Run all tests: `python -m unittest discover -s tests -v`
- Run a single test: `python -m unittest tests.test_db_hash -v` (or `tests.test_db_hash.TestClass.test_method`)
- Mint/repair a Plaid access token: `python scripts/plaid_link.py create --append` (sandbox is headless; production
  opens Plaid Link in your browser) or `python scripts/plaid_link.py repair` (Link update mode for a broken Item —
  e.g. a `NO_ACCOUNTS` error — without rotating the token)
- Seed demo data (no Plaid credentials needed): `python scripts/seed_sample_data.py`. Reads
  `SEED_DATABASE_URL`, never `DATABASE_URL` — see Architecture note below.
- Remove seeded demo data (e.g. if it was accidentally seeded into a real database):
  `python scripts/purge_sample_data.py` (dry run; add `--apply` to delete)

Run all commands from the repo root: `database/db.py` globs the migrations via the relative path
`database/migrations/`, and config loads `.env` / `.streamlit/secrets.toml` relative to the CWD.

## Architecture

Layered, single-direction data flow orchestrated by `pipeline/runner.py::run_pipeline()`:
ingest → classify/score → persist. `main.py` is a thin entry point that calls it.

- `ingestion/` — `BaseIngestor.fetch_transactions(start_date, end_date)` returns a _normalized_ DataFrame
  (`description`, `amount`, `account_name`, `source`, `date`, ...). `PlaidIngestor` is the only implementation;
  `BaseIngestor` remains as the interface seam for future sources. Each real account is ingested once per run:
  `fetch_transactions` claims an account for the first token that reveals it and skips it for later tokens, using the
  same identity tuple `canonicalize_account_keys` matches on. That is what keeps a co-owned account visible through
  two Plaid Items from delivering every transaction twice. `_post()`'s error logging is deliberately scrubbed: on a
  non-2xx response it logs only `status_code`/`error_type`/`error_code` parsed from Plaid's JSON body, never the raw
  `response.text` — the daily pipeline's stdout becomes the GitHub Actions run log, which is visible to anyone with
  repo read access, so nothing account- or transaction-identifying (e.g. an account mask) belongs in it. Keep new log
  statements in this file to that same standard.
- `analytics/` — real ML lives in `classifier.py` (TF-IDF + Linear SVM) and `outlier_detector.py` (Isolation Forest),
  but the pipeline currently uses `analytics/placeholders.py` (`build_placeholder_models`), which stamps
  `category="uncategorized"`, `outlier_score=0.0`, `is_outlier=False`. The data path is wired end-to-end before ML is
  switched on (Phase 1). When changing "the classifier," check which module `runner.py` actually imports.
- `database/` — `DatabaseClient` (psycopg v3). `ensure_schema()` runs *every* `.sql` file in `database/migrations/`
  (currently 001–013) in filename order, on every call; each must stay safe to re-run. Postgres = Supabase/Neon
  (`DATABASE_URL`). `pipeline_runs` (migration 013) is where per-run detail lives — `pipeline/runner.py::main()`
  writes one row per run via `log_pipeline_run()` (counts on success; `error_class`/a truncated `error_message` on
  failure, never a raw exception that could embed transaction content) — instead of putting that detail in the
  GitHub Actions log, which is visible to anyone with repo read access. Transaction identity, and the duplicate
  handling built on it, is the subtlest part of this layer:
  - `build_transaction_hash` hashes Plaid's `transaction_id` when the row has one, and falls back to
    `account_key|date|description|amount` only for rows without one (seed data, future non-Plaid sources). Upserts are
    idempotent via `ON CONFLICT (transaction_hash) DO UPDATE`, and because the hash tracks the `transaction_id`, a
    transaction Plaid revises (pending → posted) or re-attributes to another account is absorbed in place.
  - **Never key identity on the natural key.** `transaction_hash` is UNIQUE, so an account-scoped formula would allow
    only one row per `(account_key, date, description, amount)` and silently destroy genuine repeats — the data holds
    four separate real `IKEA $250.00` charges on one day, tapped against a $250 contactless limit. Migration 005 added
    such an index; 010 dropped it and 005 is now an intentional no-op. Do not recreate it.
  - `transactions_external_id` (migration 009) is a partial UNIQUE index on `external_id`, catching the same Plaid
    transaction stored under two accounts.
  - `reconcile_transactions` runs after every upsert in `pipeline/runner.py`. Persistence is otherwise append-only, so
    the same real transaction returning under a *new* `transaction_id` (Item re-link, or one account exposed through
    two Items) lands as a second row. Reconciliation trims stored copies per natural key down to the number Plaid
    currently returns. A natural key Plaid returns **zero** of is skipped and never touched — that is real history aged
    out of Plaid's rolling window, not a duplicate. This guard is load-bearing; do not relax it.
  - `is_duplicate` (migration 012) is a user-set flag for copies no rule can identify. Flagged rows are excluded from
    analytics but never deleted, so the call is reversible. Like `user_category` and `is_recurring`, it survives
    pipeline re-runs only because `upsert_transactions` never names that column — keep it out of the INSERT.
  - Account identity is `(official_name, account_subtype, account_type, mask)`, matched by `canonicalize_account_keys`
    (after `persistent_account_id`). `owner_name` is excluded: it records which token revealed the account, not who
    owns it.
- `core/` — shared, UI-agnostic helpers: `config.py` (`load_settings()`, `ConfigError`), `auth_session.py`,
  `google_oauth.py`.
- `app/` — Streamlit only. `streamlit_app.py` wires together `auth.py` (Google OAuth sign-in, 4-hour session expiry,
  sign-out) and `dashboard.py` (DB reads + Plotly rendering). The transactions table is where the user sets
  `is_duplicate`; a "Possible duplicates only" sidebar filter surfaces the candidates.
  **Frozen as of PLAN.md Phase 15** — it stays as a reference implementation and fallback, but new
  dashboard work goes into `web/`. Do not add features here; do not refactor it. Its *pure* helpers
  (`_enrich_transactions`, `_classify_tx_type`, `_effective_credit_limit`, `_label_subtype`) are
  deliberately still imported by `api/viewmodels.py` — the freeze forbids editing this module, not
  reusing it.
- `api/` — FastAPI backend for the React dashboard. `routers/auth.py` (Google OAuth + JWT session
  cookie + CSRF) and `routers/data.py` (read endpoints returning pre-shaped view models, plus the 5
  write paths). `viewmodels.py` builds those view models by reusing `app/dashboard.py`'s pure
  functions rather than reimplementing them, so the business logic stays covered by the existing
  dashboard tests. Two conventions matter here:
  - **Every ratio the API returns is a fraction**, not percentage points — a 60% savings rate is
    `0.6`. `pct` fields were already fractions while `savings_rate` was percentage points, and the
    frontend applied one formatter to both, so one was always wrong. Never reintroduce a `* 100`;
    formatting belongs to the UI.
  - **Series are returned wide, not long.** `{month, income, expenses, net}`, not
    `{month, tx_type, amount}`. The long shape forced the frontend to pivot on a `tx_type` string and
    it matched the wrong case, so a chart rendered axes and no bars. Keep the pivot server-side.
- `web/` — React + TypeScript dashboard (Vite, Tailwind v4, TanStack Query, Recharts). `lib/api.ts`
  owns the cross-origin cookie + CSRF concerns; `lib/types.ts` mirrors the Pydantic response models
  field-for-field and must be updated in the same change as `api/routers/data.py`, or `tsc -b` is the
  only thing standing between you and a runtime shape mismatch. There is deliberately **no sign-out
  button** (stateless JWTs, no server-side revocation — see the comment in `src/App.tsx`).
- `scripts/` — `plaid_link.py` (mint or repair a Plaid access token; see `ingestion/plaid_link.py` for the
  underlying `PlaidLinkClient`), `seed_sample_data.py` (writes deterministic demo data straight to Postgres —
  no ingestion, no credentials), and `purge_sample_data.py` (deletes it again). Seeding is intentionally
  `SEED_DATABASE_URL`-only — it never reads `DATABASE_URL` — so an accidental run cannot land demo data in a
  production database; it also refuses to write into any database already holding non-sample rows unless
  `--force` is passed. Every row the seed writes is namespaced (`accounts.source = "sample"`, `account_key`
  prefixed `sample:`, `transactions.external_id` prefixed `SAMPLE-`), which is what makes `purge_sample_data.py`
  safe to point at a real database: it only ever touches rows under `source = "sample"`.

## Configuration

`core/config.py::load_settings()` reads each key from, in precedence order: environment → `.streamlit/secrets.toml`
→ default. `DATABASE_URL` is the only value `load_settings()` requires — it raises `ConfigError` if missing.
Plaid vars (`PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ACCESS_TOKENS`) are read optionally at config-load time and
only enforced by `pipeline/runner.py::_build_ingestor` when the pipeline actually runs — this keeps the dashboard
and `scripts/seed_sample_data.py` usable with no Plaid credentials at all. See `.env.example` and the README for
the full variable list. The same env-var names are used by GitHub Actions secrets.

## Automation

`.github/workflows/daily-finance-pipeline.yml` is **defined but not yet live**: it declares a daily `cron`
(05:00 UTC) and `workflow_dispatch` to run `python main.py` with credentials injected from GitHub Secrets, but
automatic runs are not active yet — the workflow is committed but inert until required Secrets are populated on
the default branch, and GitHub only schedules workflows from the default branch (`main`). Treat scheduled
automation as a goal, not current behavior. `pipeline_runs.trigger_type` (`"schedule"` / `"workflow_dispatch"` /
`"local"`) records which of these actually produced a given run — a manual `workflow_dispatch` run and that
day's cron run are both legitimate, independent executions, so seeing two rows on the same day is expected,
not a duplicate-write bug.

## Notes

- `venv_automated_financial_intelligence/` is a local virtualenv — do not edit or search inside it.
