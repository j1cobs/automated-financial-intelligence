# automated-financial-intelligence

> Personal-finance platform: pull transactions from Plaid, persist them in PostgreSQL, and explore them in a Streamlit dashboard. Built to be self-hosted.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg) ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)

## Screenshots

<!-- Add screenshots here once captured on sample data. -->

## Architecture

```
                 ┌─────────────┐      ┌──────────────────────┐      ┌──────────┐      ┌───────────┐
  Plaid API ──▶ │ ingestion/  │ ──▶  │ pipeline/runner.py   │ ──▶ │ Postgres │ ──▶  │ dashboard │
                 └─────────────┘      │ (classify + score)   │      └──────────┘      └───────────┘
                                      └──────────────────────┘             ▲
                                                                           │
                              scripts/seed_sample_data.py ─────────────────┘
                              (writes demo data straight to the DB, no Plaid needed)
```

| Layer     | Path                 | Responsibility                                                                            |
| --------- | -------------------- | ----------------------------------------------------------------------------------------- |
| Ingestion | `ingestion/`         | Fetch and normalize transactions (Plaid; `BaseIngestor` is the seam for future sources)   |
| Database  | `database/`          | Idempotent upserts keyed on a content hash; migrations run automatically on startup       |
| Analytics | `analytics/`         | ML classifier and outlier detector (the pipeline uses a placeholder for now, see Roadmap) |
| Core      | `core/`              | Config loading, Google OAuth/PKCE, session handling                                       |
| Pipeline  | `pipeline/runner.py` | Orchestrates ingest → classify → persist                                                  |
| App       | `app/`               | Streamlit dashboard, four tabs, English/French                                            |

A few decisions worth calling out:

- **Idempotent upserts.** Every transaction hashes to `sha256(account_key|date|description|amount)`, so re-running the pipeline on the same window is a no-op instead of a pile of duplicates.
- **Config-load vs. pipeline-run validation are separate.** `load_settings()` only ever requires `DATABASE_URL`. Plaid credentials are checked when the pipeline actually runs, not at import time, so the dashboard and the sample-data seed script both work with zero Plaid setup.
- **Migrations run at every startup**, not through a separate tool. `ensure_schema()` just executes every `.sql` file in `database/migrations/` in order; each one is written to be safe to run twice.
- **Manual edits survive pipeline re-runs.** The pipeline writes to `category`; a user editing a row in the dashboard writes to `user_category` instead, and the dashboard reads `COALESCE(user_category, category)`. Same pattern for `is_recurring`.
- **OAuth without a framework.** Google sign-in uses PKCE (S256) directly against Google's endpoints, with a verified-email allowlist and a 4-hour session.

## Quickstart (local, no Plaid account needed)

```bash
docker compose up -d
python scripts/seed_sample_data.py
streamlit run app/streamlit_app.py
```

Requires Python 3.12+, and every command runs from the repo root (config and migration paths are relative). Plaid credentials are only needed if you want to pull real transactions with `python main.py`. See [docs/setup-plaid.md](docs/setup-plaid.md) for that.

## Configuration reference

All configuration is read by `core/config.py::load_settings()`, in this order: environment variables → `.streamlit/secrets.toml` → default. See `.env.example` for a filled-in template.

| Variable                     | Required                     | Default                       | Notes                                                                                   |
| ---------------------------- | ---------------------------- | ----------------------------- | --------------------------------------------------------------------------------------- |
| `DATABASE_URL`               | Yes                          | none                          | The only variable `load_settings()` enforces. TLS is auto-appended for non-local hosts. |
| `GOOGLE_OAUTH_CLIENT_ID`     | For the dashboard            | none                          | See [docs/setup-google-oauth.md](docs/setup-google-oauth.md)                            |
| `GOOGLE_OAUTH_CLIENT_SECRET` | For the dashboard            | none                          |                                                                                         |
| `GOOGLE_OAUTH_REDIRECT_URI`  | For the dashboard            | none                          | Must exactly match the URI registered in the Google console                             |
| `GOOGLE_ALLOWED_EMAILS`      | For the dashboard            | none                          | Comma-separated allowlist; empty means nobody can sign in                               |
| `PLAID_CLIENT_ID`            | For the pipeline             | none                          | Not needed for the dashboard or the seed script                                         |
| `PLAID_SECRET`               | For the pipeline             | none                          |                                                                                         |
| `PLAID_ACCESS_TOKENS`        | For the pipeline             | none                          | Comma-separated                                                                         |
| `PLAID_ACCESS_TOKEN_OWNERS`  | Optional                     | none                          | Comma-separated, positionally aligned with `PLAID_ACCESS_TOKENS`                        |
| `PLAID_BASE_URL`             | Optional                     | `https://sandbox.plaid.com`   |                                                                                         |
| `SUPABASE_URL`               | Optional                     | none                          | Only used for a sidebar caption when signed in                                          |
| `MODEL_PATH`                 | Optional (Phase 7, deferred) | `artifacts/classifier.joblib` |                                                                                         |
| `LABELED_DATASET_PATH`       | Optional (Phase 7, deferred) | `labeled_transactions.csv`    |                                                                                         |

## Ingesting your own data

Pulling real transactions requires a Plaid account and a Postgres database. See [docs/setup-plaid.md](docs/setup-plaid.md) and [docs/setup-database.md](docs/setup-database.md).

## Project status & roadmap

- **Done:** ingest → classify → persist → dashboard, end to end. Four-tab dashboard (Overview, Cash flow, Budget, Transactions), bilingual EN/FR, inline category and recurring-flag editing, budgets, anomaly surfacing.
- **Stubbed:** the ML classifier and outlier detector exist in `analytics/`, but the pipeline currently runs `analytics/placeholders.py` instead. Every transaction is stamped `Uncategorized` with `outlier_score=0` until Phase 7 wires the real models in.
- **Not yet active:** the daily GitHub Actions pipeline is defined in `.github/workflows/daily-finance-pipeline.yml` but doesn't run automatically until the required Secrets are populated on `main` (GitHub only schedules workflows from the default branch). See [docs/deployment.md](docs/deployment.md).

## Security

- **Auth:** Google OAuth with PKCE (S256) and a verified-email allowlist that fails closed: an empty `GOOGLE_ALLOWED_EMAILS` means nobody can sign in. Sessions expire after 4 hours.
- **Transport:** TLS is enforced in code for any non-local database host; `sslmode=require` is appended automatically unless the URL already specifies one.
- **At rest:** data is encrypted at rest by the managed Postgres provider (Supabase or Neon). Application-level column encryption was considered and rejected. It would break the SQL aggregation the dashboard depends on, and it doesn't add meaningful protection against the realistic threat here, which is a leaked connection string. Credential rotation covers that case instead.
- **Secrets:** everything lives in environment variables or GitHub Secrets; nothing is committed. Dependencies are installed from a hash-locked file (`pip install --require-hashes -r requirements.lock`).
- **Public/mobile deployments:** require an HTTPS OAuth redirect URI. Database errors are logged server-side and never rendered to the browser.

## Contributing / License

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
