# automated-financial-intelligence

> Personal-finance platform: pull transactions from Plaid, persist them in PostgreSQL, and explore them in a React dashboard backed by a FastAPI service. Built to be self-hosted.

![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg) ![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)

## Screenshots

All captured on generated sample data (`scripts/seed_sample_data.py`) — no real financial information.

| Overview | Cash flow |
| --- | --- |
| ![Overview tab — net worth trend, credit utilization, top merchants, spending by category](docs/images/overview.png) | ![Cash Flow tab — income vs. expenses by month and week, rolling 30-day spend](docs/images/cashflow.png) |

| Budget | Transactions |
| --- | --- |
| ![Budget tab — monthly category limits with projected end-of-month spend, forecast and savings goals](docs/images/budget.png) | ![Transactions tab — ledger with inline category editing and recurring and duplicate flags](docs/images/transactions.png) |

## Architecture

```
                 ┌─────────────┐      ┌──────────────────────┐      ┌──────────┐      ┌───────────┐
  Plaid API ──▶ │ ingestion/  │ ──▶  │ pipeline/runner.py   │ ──▶ │ Postgres │ ──▶  │ api + web │
                 └─────────────┘      │ (classify + score)   │      └──────────┘      └───────────┘
                                      └──────────────────────┘             ▲
                                                                           │
                              scripts/seed_sample_data.py ─────────────────┘
                              (writes demo data straight to the DB, no Plaid needed)
```

| Layer     | Path                 | Responsibility                                                                            |
| --------- | -------------------- | ----------------------------------------------------------------------------------------- |
| Ingestion | `ingestion/`         | Fetch and normalize transactions (Plaid; `BaseIngestor` is the seam for future sources)   |
| Database  | `database/`          | Idempotent upserts keyed on Plaid's transaction id; migrations run automatically on startup |
| Analytics | `analytics/`         | Categorization cascade, rule-based anomaly detection, recurring streams, budgets, forecast, goals |
| Core      | `core/`              | Config loading, Google OAuth/PKCE, session handling                                       |
| Pipeline  | `pipeline/runner.py` | Orchestrates ingest → classify → persist                                                  |
| API       | `api/`               | FastAPI backend: Google sign-in, session cookie, pre-shaped view models for the dashboard |
| Web       | `web/`               | React + TypeScript dashboard (Vite), four tabs, English                                   |

A few decisions worth calling out:

- **Idempotent upserts.** A transaction is identified by Plaid's `transaction_id`, hashed into a unique `transaction_hash` (rows with no id — seed data — fall back to `account_key|date|description|amount`). Re-running the pipeline on the same window is a no-op instead of a pile of duplicates, and a pending charge that posts under revised amounts updates its row rather than twinning it.
- **Duplicate detection is not a unique index, deliberately.** Nothing in `(account_key, date, description, amount)` separates a duplicate from a genuine repeat: the four `IKEA $250.00` charges in this data are four real taps against a $250 contactless limit, and an index on that key destroys three of them. So the pipeline stays append-only and `reconcile_transactions()` trims stored copies down to however many Plaid itself currently returns for each key — with the rule that a key Plaid returns *zero* of is never touched, because that is real history aged out of Plaid's window. What no rule can settle, the user flags as a duplicate in the dashboard; flagged rows drop out of every analytic but stay in the ledger, so the call is reversible.
- **Config-load vs. pipeline-run validation are separate.** `load_settings()` only ever requires `DATABASE_URL`. Plaid credentials are checked when the pipeline actually runs, not at import time, so the dashboard and the sample-data seed script both work with zero Plaid setup.
- **Migrations run at every startup**, not through a separate tool. `ensure_schema()` just executes every `.sql` file in `database/migrations/` in order; each one is written to be safe to run twice.
- **Manual edits survive pipeline re-runs.** The pipeline writes to `category`; a user editing a row in the dashboard writes to `user_category` instead, and the dashboard reads `COALESCE(user_category, category)`. Same pattern for `is_recurring` and the duplicate flag: the upsert never names those columns, so nothing the pipeline writes can clobber them.
- **OAuth without a framework.** Google sign-in uses PKCE (S256) directly against Google's endpoints, with a verified-email allowlist and a 1-hour session.

## Quickstart (local, no Plaid account needed)

```bash
cp .env.example .env          # the defaults already point at the docker database
docker compose up -d          # Postgres on 127.0.0.1:5433
python scripts/seed_sample_data.py
uvicorn api.main:app --reload     # the API, port 8000 by default
cd web && npm run dev             # the React dashboard, in a second terminal
```

That gives you 5 sample accounts and ~140 generated transactions across a trailing 120-day window, complete with categories and three planted anomalies — enough to exercise every tab. The seed writes straight to the database, so no Plaid account is involved.

The seed script reads `SEED_DATABASE_URL`, not `DATABASE_URL` — a separate variable so a stray run can never write demo data into a real database. `.env.example` points it at the same local docker instance as `DATABASE_URL` by default. It also refuses to seed any database that already holds non-sample rows (pass `--force` to override). To undo an accidental seed into a real database, run `python scripts/purge_sample_data.py` (dry run by default; add `--apply` to delete).

Requires Python 3.12+, Docker and Node.js (for `web/`). Every command runs from the repo root (config and migration paths are relative). Plaid credentials are only needed to pull real transactions with `python main.py` — see [docs/setup-plaid.md](docs/setup-plaid.md).

Signing in still needs Google OAuth credentials and a session secret in `.env` (`GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8000/auth/google/callback`, `JWT_SECRET`, and your own address in `GOOGLE_ALLOWED_EMAILS`); the dashboard is gated behind it. `FRONTEND_ORIGIN` must match the port Vite prints (`.env.example` defaults it to `http://localhost:5173`).

> **Use `127.0.0.1`, not `localhost`, in `DATABASE_URL`.** Compose binds the port on IPv4 only, and on Windows `localhost` resolves to `::1` first — so every connection waits for the IPv6 attempt to time out. That is ~15s per connection instead of 0.1s, which makes the seed script look like it has frozen.

To reset the demo data, recreate the volume — the seed reassigns its sample ids after a date sort, so re-seeding on a *later* day than the last run collides with the stored `external_id`s rather than updating them:

```bash
docker compose down -v && docker compose up -d && python scripts/seed_sample_data.py
```

## React dashboard (`web/` + `api/`)

The dashboard is a React + TypeScript app (`web/`) talking to a FastAPI backend (`api/`). To run it
locally, in two terminals:

```bash
uvicorn api.main:app --reload    # the API, port 8000 by default
cd web && npm run dev            # the React dashboard, needs the API running
```

The browser only calls the relative `/api` prefix: Vite proxies it to `http://localhost:8000` in dev
(`web/vite.config.ts`), and Vercel rewrites it to the deployed API in production (`web/vercel.json`),
so the session cookie is first-party in both. See [docs/deployment.md](docs/deployment.md). The UI is
English-only; `web/src/lib/strings.ts` is the module a second locale would translate.

Four tabs: **Overview** (net worth trend, credit utilization, top merchants, recurring and committed
spend, category drift against your own baseline, and spending by category), **Cash Flow**,
**Budget** (per-month category caps with carry-forward, a forward cash-flow forecast, and savings
goals), and **Transactions** (its ledger table virtualizes automatically above 50 rows, for performance
on large transaction histories). The former Streamlit dashboard was removed; see
[ADR 0013](docs/adr/0013-decommission-streamlit.md).

## Configuration reference

All configuration is read by `core/config.py::load_settings()`, in this order: environment variables → `.env` → default. See `.env.example` for a filled-in template.

| Variable                     | Required                     | Default                       | Notes                                                                                   |
| ---------------------------- | ---------------------------- | ----------------------------- | --------------------------------------------------------------------------------------- |
| `DATABASE_URL`               | Yes                          | none                          | The only variable `load_settings()` enforces. TLS is auto-appended for non-local hosts. |
| `SEED_DATABASE_URL`          | For `seed_sample_data.py`    | none                          | Seed script writes here only, never to `DATABASE_URL`. TLS auto-appended for non-local hosts. |
| `GOOGLE_OAUTH_CLIENT_ID`     | For the API (sign-in)        | none                          | See [docs/setup-google-oauth.md](docs/setup-google-oauth.md)                            |
| `GOOGLE_OAUTH_CLIENT_SECRET` | For the API (sign-in)        | none                          |                                                                                         |
| `GOOGLE_OAUTH_REDIRECT_URI`  | For the API (sign-in)        | none                          | The API's `/auth/google/callback`; must exactly match the URI registered in the Google console |
| `GOOGLE_ALLOWED_EMAILS`      | For the API (sign-in)        | none                          | Comma-separated allowlist; empty means nobody can sign in                               |
| `JWT_SECRET`                 | For the API (sign-in)        | none                          | Signs the session cookie; no session is minted without it                               |
| `FRONTEND_ORIGIN`            | For the API                  | none                          | The React app's origin: the CORS allow-list entry and the post-sign-in redirect target  |
| `PLAID_CLIENT_ID`            | For the pipeline             | none                          | Not needed for the dashboard or the seed script, except balance refresh through the API |
| `PLAID_SECRET`               | For the pipeline             | none                          |                                                                                         |
| `PLAID_ACCESS_TOKENS`        | For the pipeline             | none                          | Comma-separated                                                                         |
| `PLAID_ACCESS_TOKEN_OWNERS`  | Optional                     | none                          | Comma-separated, positionally aligned with `PLAID_ACCESS_TOKENS`                        |
| `PLAID_BASE_URL`             | Optional                     | `https://sandbox.plaid.com`   |                                                                                         |
| `SUPABASE_URL`               | Optional                     | none                          | Read into settings; nothing currently uses it                                           |
| `MODEL_PATH`                 | Optional (Phase 7, deferred) | `artifacts/classifier.joblib` |                                                                                         |
| `LABELED_DATASET_PATH`       | Optional (Phase 7, deferred) | `labeled_transactions.csv`    |                                                                                         |

## Ingesting your own data

Pulling real transactions requires a Plaid account and a Postgres database. See [docs/setup-plaid.md](docs/setup-plaid.md) and [docs/setup-database.md](docs/setup-database.md).

## Project status & roadmap

- **Done:** ingest → classify → persist → dashboard, end to end. Four-tab React dashboard (Overview, Cash Flow, Budget, Transactions), inline category, recurring- and duplicate-flag editing, per-month budgets with carry-forward, a cash-flow forecast, savings goals, rule-based anomaly surfacing, manual credit-limit entry for cards where Plaid reports no limit, and warnings for stale balances and duplicate accounts.
- **Categorization and anomalies:** transactions are categorized by a cascade (your merchant corrections, then Plaid's category, then `UNCATEGORIZED`). Anomaly detection is deliberately rule-based, not ML (see [ADR 0007](docs/adr/0007-anomaly-detection-without-ml.md)); the TF-IDF classifier in `analytics/` is unused.
- **Not yet active:** the daily GitHub Actions pipeline is defined in `.github/workflows/daily-finance-pipeline.yml` but doesn't run automatically until the required Secrets are populated on `main` (GitHub only schedules workflows from the default branch). See [docs/deployment.md](docs/deployment.md).

## Security

- **Auth:** Google OAuth with PKCE (S256) and a verified-email allowlist that fails closed: an empty `GOOGLE_ALLOWED_EMAILS` means nobody can sign in. Sessions expire after 1 hour.
- **Transport:** TLS is enforced in code for any non-local database host; `sslmode=require` is appended automatically unless the URL already specifies one.
- **At rest:** data is encrypted at rest by the managed Postgres provider (Supabase or Neon). Application-level column encryption was considered and rejected. It would break the SQL aggregation the dashboard depends on, and it doesn't add meaningful protection against the realistic threat here, which is a leaked connection string. Credential rotation covers that case instead.
- **Secrets:** everything lives in environment variables or GitHub Secrets; nothing is committed. Dependencies are installed from a hash-locked file (`pip install --require-hashes -r requirements.lock`).
- **Public/mobile deployments:** require an HTTPS OAuth redirect URI. Database errors are logged server-side and never rendered to the browser.

## Contributing / License

See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).
