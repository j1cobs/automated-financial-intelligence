# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a Phase-1 build: the data path (ingest → process → persist → dashboard) is wired end-to-end first, ahead of
the full feature set described in the original design brief. What this means concretely:
- ML is stubbed — `pipeline/runner.py` uses `analytics/placeholders.py`, not the real `analytics/classifier.py` /
  `analytics/outlier_detector.py` yet (see Architecture).
- The dashboard implements core views; some target views (e.g. rolling burn-rate, household combined-vs-individual
  breakdowns) are not all built out.
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

## Commands

- Install deps: `pip install -r requirements.txt` (requirements.txt is authoritative; pyproject.toml is minimal/incomplete)
- Run pipeline: `python main.py`
- Run dashboard: `streamlit run app/streamlit_app.py`
- Run all tests: `python -m unittest discover -s tests -v`
- Run a single test: `python -m unittest tests.test_db_hash -v` (or `tests.test_db_hash.TestClass.test_method`)
- Plaid sandbox bootstrap: `python scripts/generate_public_token.py sandbox --append`

Run all commands from the repo root: `database/db.py` reads the migration file via the relative path
`database/migrations/001_core_tables.sql`, and config loads `.env` / `.streamlit/secrets.toml` relative to the CWD.

## Architecture

Layered, single-direction data flow orchestrated by `pipeline/runner.py::run_pipeline()`:
ingest → classify/score → persist. `main.py` is a thin entry point that calls it.

- `ingestion/` — `BaseIngestor.fetch_transactions(start_date, end_date)` returns a *normalized* DataFrame
  (`description`, `amount`, `account_name`, `source`, `date`, ...). `CSVIngestor` and `PlaidIngestor` are the two
  implementations; `runner._build_ingestor` picks one based on `settings.ingestion_source`.
- `analytics/` — real ML lives in `classifier.py` (TF-IDF + Linear SVM) and `outlier_detector.py` (Isolation Forest),
  but the pipeline currently uses `analytics/placeholders.py` (`build_placeholder_models`), which stamps
  `category="uncategorized"`, `outlier_score=0.0`, `is_outlier=False`. The data path is wired end-to-end before ML is
  switched on (Phase 1). When changing "the classifier," check which module `runner.py` actually imports.
- `database/` — `DatabaseClient` (psycopg v3). `ensure_schema()` executes the SQL migration file at runtime;
  upserts are idempotent via `build_transaction_hash` (sha256 of `account_name|date|description|amount`) with
  `ON CONFLICT (transaction_hash) DO UPDATE`. Postgres = Supabase/Neon (`DATABASE_URL`).
- `core/` — shared, UI-agnostic helpers: `config.py` (`load_settings()`, `PlaidLinkConfig`, `ConfigError`),
  `auth_session.py`, `google_oauth.py`, `plaid.py`.
- `app/` — Streamlit only. `streamlit_app.py` wires together `auth.py` (Google OAuth sign-in, 4-hour session expiry,
  sign-out) and `dashboard.py` (DB reads + Plotly/Altair rendering).
- `scripts/` — Plaid Link bootstrap helpers (`generate_public_token.py`, `create_sandbox_access_token.py`).

## Configuration

`core/config.py::load_settings()` reads each key from, in precedence order: environment → `.streamlit/secrets.toml`
→ default. Missing required values raise `ConfigError`. `INGESTION_SOURCE` (`csv` | `plaid`, default `csv`) decides
which ingestor runs and which vars become required (`CSV_PATHS` for csv; `PLAID_CLIENT_ID`/`PLAID_SECRET`/
`PLAID_ACCESS_TOKENS` for plaid). `DATABASE_URL` is always required. See `.env.example` and the README for the full
variable list. The same env-var names are used by GitHub Actions secrets.

## Automation

`.github/workflows/daily-finance-pipeline.yml` is **defined but not yet live**: it declares a daily `cron`
(07:00 UTC) and `workflow_dispatch` to run `python main.py` with credentials injected from GitHub Secrets, but
automatic runs are not active yet — the workflow is still on the `dev` branch and uncommitted, and GitHub only
schedules workflows from the default branch (`main`) once the required Secrets are populated. Treat scheduled
automation as a goal, not current behavior.

## Notes

- `venv_automated_financial_intelligence/` is a local virtualenv — do not edit or search inside it.
