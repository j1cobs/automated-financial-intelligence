# Publish-Readiness + Dashboard Expansion Plan

> Working plan to make this repo publishable on GitHub (interview showcase + self-host template) **and** expand the dashboard with meaningful financial insights.
> Status: **in progress** — tick checkboxes as work lands. Safe to delete once all phases complete.
> Phase numbers reflect the order things were *designed*, not the order they should now be *done* — see
> "Where things stand" below for the current ranking. Phase 3 (dashboard) is the largest; it has strict
> internal ordering.
>
> **Decision (2026-07-07): ingestion is Plaid-only.** Phase 2 deletes the CSV ingestor and everything that
> served it. The zero-credential demo path is a **DB seed script** that writes curated sample data directly
> into Postgres via `DatabaseClient` — no ingestion involved. Plaid credentials are enforced by the
> *pipeline*, never by `load_settings()`, so the seed demo and dashboard-only deployments need no Plaid keys.
>
> **Security (2026-07-07): Phase 2.5 is a publish blocker.** A full security review challenged the current
> implementation (findings inline in Phase 2.5); the hardening work lives in Phase 2.5 (code), plus
> amendments in Phases 0, 1f (lockfile), 4 (docs), and 5 (CI). Phase 2.5, Phase 5, and 1f must all land
> before the `dev → main` publish merge — the dashboard is deployed on the public internet (mobile sign-in
> for two allowlisted users), so internet-facing posture is not optional.

---

## Where things stand (updated 2026-08-22)

**Complete:** Phases 1, 2, 2.5, 2.6, 2.6a, 2.7, 2.8, 3 (3a–3s, all), 4, 5, 8a, 10 (10a–10i all done — both
allowlisted accounts confirmed on desktop and mobile, non-allowlisted account correctly refused), 11, 12, 13
(production purge confirmed run — demo/sample accounts are gone from the live database), 14 (code committed
as `d9e1a9f` and live-run verified 2026-08-22 — no leaked data, correct `pipeline_runs` row), and Phase 6
except the optional pytest migration.
**Partial:** Phase 0 (only README screenshots remain — the HTTPS redirect URI item closed 2026-07-26), Phase
8 (8a done; 8b's manual checklist is a pre-merge ritual, not code).
**In progress:** Phase 9 (9a–9f implemented on `dev` 2026-07-27, uncommitted; the 9g device-verification
matrix is outstanding and gates the phase).
**Deferred by choice:** Phase 7 (ML), Appendix A, 6h (pytest).

> **All prior gaps resolved.** The `dev → main` merge is done — `origin/main` is now at `7379d4f` ("fix(db):
> deduplicate transactions + fix ui"), and `origin/dev` is confirmed an ancestor of `origin/main` via `git
> merge-base --is-ancestor`. Phase 12 (transaction identity rewrite + `reconcile_transactions`) is on `main`,
> so the GitHub Actions cron now runs the corrected append/reconcile logic — the double-ingestion and
> duplicate-recreation bug from 2026-07-27 is resolved in production. The dashboard is deployed live on
> Streamlit Community Cloud, and sign-in is confirmed working end-to-end (desktop, `jacosse1@gmail.com`,
> real data rendering correctly).

The dashboard is live and reachable, sign-in works on both desktop and mobile (both allowlisted accounts
confirmed, non-allowlisted correctly refused), and the daily cron runs the correct dedup logic — the
publish-critical path, including Phase 10i verification in full, is done. What's left is a mobile *UX*
polish pass and feature work, not blockers.

### Recommended order of work

Ranked by what unblocks the most, not by phase number.

| # | Work | Why here | Effort |
|---|---|---|---|
| 1 | **Phase 9 — 9g visual verification** | 9a–9f are implemented on `dev` (2026-07-27); 152 tests and lint pass, and a browser pass confirmed the stylesheet reaches the DOM with all rules valid (it also caught a bug that had been voiding the whole stylesheet — see Phase 9). But **nothing has been looked at on a narrow viewport**: Chrome would not size below ~1660px and the dashboard sits behind sign-in. 2-up KPI wrap, legend placement, table behaviour and FR tab fit are all still unseen. Needs DevTools device emulation + a signed-in session. | ~30 min |
| 2 | **Phase 7** — ML activation | Deferred by design; the placeholder seam means this changes no orchestration. | Large |
| 3 | **Appendix A** — interactivity extras | Explicitly non-blocking. | Varies |

**What changed in this ranking:** Phase 10i is now **fully closed out** — both allowlisted accounts
confirmed working, a non-allowlisted account confirmed refused, and mobile sign-in confirmed working
end-to-end (2026-07-27). Phase 13's production purge is confirmed done (2026-08-22) — the accidental sample
data is gone from the live database. Phase 14 is now **fully closed** (2026-08-22) — code committed and its
live-run verification confirmed working. No blockers remain anywhere in the plan; the only thing left before
everything else is deferred feature work is **Phase 9g** (mobile visual verification).

---

## Phase 0 — Owner actions (no code; checklist)

The local untracked `.env` holds **live production credentials**. Git history is verified clean but rotate as a precaution:

- [x] Rotate Supabase DB password; update local `.env` + GitHub Secrets.
- [x] Rotate Plaid production secret; re-issue all three access tokens. Done 2026-07-17 — re-linking the
  Item minted new `account_id`s for existing accounts, so `scripts/dedupe_accounts.py` was run (dry run,
  then `--apply`) to merge the resulting duplicates (see Phase 2.7).
- [x] Rotate (or recreate) the Google OAuth client secret.
- [x] Set the production Google OAuth redirect URI to the **HTTPS** public dashboard URL (mobile sign-in
  depends on it); keep `http://localhost:8501/` only as a second, dev-only redirect in the Google console.
  **Done 2026-07-26** — the SCC URL is registered in Google Cloud Console alongside `http://localhost:8501/`,
  and sign-in is confirmed working live (see Phase 10i). Mobile sign-in itself is not yet verified (Phase 9
  is not started) — this checkbox covers the redirect URI registration, not full mobile verification.
- [x] Confirm `GOOGLE_ALLOWED_EMAILS` in production secrets lists exactly the two authorized addresses.
- [x] Confirm the managed Postgres (Supabase/Neon) tier has encryption at rest enabled. **Confirmed** — all
  customer data is encrypted at rest on the provider.
- [x] At publish time: merge `dev` → `main`, populate GitHub Secrets (cron only runs from the default
  branch). **Done 2026-07-20.** `main` is now `b27090a` ("feat(app): first real push to main, v1 of
  dashboard and pipeline") and contains every commit from `dev` (GitHub `compare/main...dev` reports
  `ahead_by=0, behind_by=1`). **Consequence: the daily pipeline cron is now live** — the workflow sits on
  the default branch and the Secrets it needs are populated, so the Automation caveat below (and the
  matching one in `CLAUDE.md`) is obsolete and must be corrected. Note that a *local* `git fetch` is still
  required: local `main` is stale at `fa80b46` and local `dev` is 1 commit behind `origin/main`.
- [ ] Capture dashboard screenshots on sample data for the README (leave placeholder section, don't block merge).

---

## Phase 1 — Hygiene / config truth

All changes are straightforward edits. Do them together in one commit titled "chore: hygiene and config truth".

### 1a. `.gitignore`
Append after the "Environments" block:
```
artifacts/
data/
labeled_transactions.csv
*.joblib
```
Rationale: `artifacts/` is the default `MODEL_PATH` dir; `data/` is reserved for locally generated files (e.g. the Phase 7 labeled dataset) and must never be committed.

### 1b. `.env.example`
**Delete** lines 17-23 (the 7 dead `PLAID_LINK_*` variables — nothing in `core/config.py` reads them):
```
PLAID_LINK_CLIENT_NAME=...
PLAID_LINK_USER_ID=...
PLAID_LINK_PRODUCTS=...
PLAID_LINK_COUNTRY_CODES=...
PLAID_LINK_LANGUAGE=...
PLAID_LINK_WEBHOOK=...
PLAID_LINK_REDIRECT_URI=...
```

**Delete** the `INGESTION_SOURCE` and `CSV_PATHS` lines — CSV ingestion is removed in Phase 2a and the
config keys go with it.

**Change** the demo default so the file works out-of-the-box with docker (Phase 2c):
```env
DATABASE_URL=postgresql://finance:finance@localhost:5433/finance
```

**Add** this missing optional var (read by `core/config.py:119`):
```env
# SUPABASE_URL=https://yourproject.supabase.co
```
Note: `SUPABASE_SERVICE_ROLE_KEY` was traced to zero usages in the codebase (2026-07-07) and is
intentionally omitted; `SUPABASE_URL` is kept because `app/auth.py:142-143` uses it for a sidebar caption.

Note: the docker Postgres service maps to host port **5433**, not 5432 — verified during Phase 2
implementation (2026-07-07) that a native Postgres Windows service already occupies 5432 on the dev
machine, silently swallowing connections meant for the container. `DATABASE_URL` and `docker-compose.yml`
(2c) both use 5433 to avoid that conflict; adjust back to 5432 if your own machine has no such conflict.

**Final group structure** for clarity:
```
# ── Required ────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://finance:finance@localhost:5433/finance
# Production example — TLS is auto-enforced for remote hosts (Phase 2.5a), but be explicit:
# DATABASE_URL=postgresql://user:pass@host:5432/db?sslmode=require

# ── Plaid (required to run the pipeline; NOT needed for the seed demo or dashboard) ──
# PLAID_CLIENT_ID=...
# PLAID_SECRET=...
# PLAID_ACCESS_TOKENS=token1,token2
# PLAID_ACCESS_TOKEN_OWNERS=Alex,Sam
# PLAID_BASE_URL=https://sandbox.plaid.com

# ── Google OAuth (required for dashboard) ───────────────────────────────────
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501/
# Production deployments MUST use an https:// redirect URI (mobile/public sign-in)
GOOGLE_ALLOWED_EMAILS=email1@gmail.com,email2@gmail.com

# ── Supabase (optional — only if using Supabase instead of docker) ──────────
# SUPABASE_URL=https://yourproject.supabase.co

# ── ML artifacts (used in Phase 7, deferred) ────────────────────────────────
# MODEL_PATH=artifacts/classifier.joblib
# LABELED_DATASET_PATH=labeled_transactions.csv
```

### 1c. `pyproject.toml`
Replace the entire file with:
```toml
[build-system]
requires = ["setuptools>=70"]
build-backend = "setuptools.build_meta"

[project]
name = "automated-financial-intelligence"
version = "0.1.0"
description = "Modular personal-finance platform: ingest → classify → persist → dashboard"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dynamic = ["dependencies"]

[tool.setuptools.dynamic]
dependencies = { file = ["requirements.txt"] }

[tool.setuptools.packages.find]
include = ["analytics*", "app*", "core*", "database*", "ingestion*", "pipeline*"]
```

### 1d. `requirements.txt`
Remove the `altair` line (never imported anywhere in the codebase — verified). Keep everything else exactly as-is.

### 1e. `CLAUDE.md`
Make these targeted edits (do NOT rewrite; only fix the wrong parts). Apply them **after** Phase 2a so the
Plaid-only descriptions are true when written:

- **Line 35** (Plaid sandbox bootstrap): change `python scripts/generate_public_token.py sandbox --append` → `python scripts/create_sandbox_access_token.py --append`; add `python scripts/seed_sample_data.py` as the demo-data command.
- **Lines 11-12** (Phase 1 status paragraph): remove "rolling burn-rate" and "household combined-vs-individual breakdowns" from the "not built" list. Rewrite to: "The dashboard implements all core views. Only ML is stubbed — the pipeline uses placeholders."
- **Architecture / ingestion bullet**: remove `CSVIngestor` and `runner._build_ingestor` source-switching description — `PlaidIngestor` is the only implementation; `BaseIngestor` remains as the interface seam for future sources.
- **Configuration section**: remove `PlaidLinkConfig` (doesn't exist) and the `INGESTION_SOURCE`/`CSV_PATHS` description. Plaid vars are required *to run the pipeline* but optional at config-load time. Should read: `core/` — shared helpers: `config.py` (`load_settings()`, `ConfigError`), `auth_session.py`, `google_oauth.py`.
- **Scripts bullet**: remove `scripts/generate_public_token.py` reference; replace with `scripts/seed_sample_data.py` (Phase 2b).
- **Lines 72-75** (Automation section): replace "still on the dev branch and uncommitted" with "committed but inert until required Secrets are populated on the default branch." **Superseded 2026-07-20** — the `dev → main` merge landed and the Secrets are populated, so the workflow is no longer inert. `CLAUDE.md`'s Automation section must now say the daily cron is **live**, and the same correction applies to this plan's own Automation caveat.
- **Line 58** (dashboard description): remove "Altair" — the dashboard uses Plotly only.

### 1f. Dependency lockfile with hashes (supply chain)

`requirements.txt` is all `>=` floors — CI and every fresh install resolve to whatever is newest on PyPI at
run time. For a secrets-bearing daily job (Plaid + `DATABASE_URL` in env) that is a supply-chain exposure:
a hijacked release of any dependency executes with the credentials. Decision (2026-07-07): **lockfile with
hashes** (chosen over bare `==` pins — hashes also defeat a re-uploaded/compromised artifact of the same
version).

- Keep `requirements.txt` as the loose *direct-deps* file (human-edited, unchanged role).
- Add `pip-tools` as a dev-only tool (not in `requirements.txt`) and generate the lock:
  ```bash
  pip install pip-tools
  pip-compile --generate-hashes --output-file=requirements.lock requirements.txt
  ```
- Commit `requirements.lock`. Local + CI installs become:
  ```bash
  pip install --require-hashes -r requirements.lock
  ```
- Upgrade flow (document in CONTRIBUTING.md, Phase 4f): edit `requirements.txt` → re-run `pip-compile
  --generate-hashes` → commit both files.
- `pyproject.toml` (1c) still reads `requirements.txt` for its dynamic deps — no change needed there; the
  lock is an install-time artifact only.

---

## Phase 2 — Plaid-only refactor + demo path

### 2a. Remove the CSV ingestion path (implement first — everything downstream assumes Plaid-only)

CSV ingestion is dropped entirely. Plaid already delivers everything the CSV path needed bolted on:
`upsert_plaid_accounts` persists `owner_name`, `account_type`, `account_subtype`, and balances, so the
dashboard's owner filter and account metadata work out of the box.

**Delete outright:**
- `ingestion/csv_ingestor.py`
- `tests/test_csv_ingestor.py`
- `database/db.py::upsert_accounts` (lines 85-100) — dead code once the runner's csv branch is gone; the
  Plaid path uses `upsert_plaid_accounts`.

**Keep** `ingestion/base.py` (`BaseIngestor`) — it documents the ingestor interface and costs nothing.

#### File: `core/config.py`

- Remove `ingestion_source` and `csv_paths` from `Settings`.
- Remove the `INGESTION_SOURCE` read + validation and the entire `csv_paths` block from `load_settings()`.
- Read the Plaid values **unconditionally but optionally**: `plaid_client_id`, `plaid_secret` may be `None`;
  `plaid_access_tokens` / `plaid_access_token_owners` may be empty lists. **Do NOT raise `ConfigError` for
  missing Plaid vars in `load_settings()`** — the dashboard and the seed script (2b) only need
  `DATABASE_URL`, and a hard requirement here would break both. Required-ness moves to the pipeline (below).

#### File: `pipeline/runner.py`

- Delete the `CSVIngestor` import and `_build_ingestor`'s csv fallback. `_build_ingestor` always returns a
  `PlaidIngestor` and raises `ConfigError` when `plaid_client_id`, `plaid_secret`, or `plaid_access_tokens`
  is missing/empty (same messages as today, minus the "when INGESTION_SOURCE=plaid" suffix). Also raise
  `ConfigError` if `plaid_access_token_owners` is non-empty but its length differs from
  `plaid_access_tokens` — a silent misalignment mislabels account owners.
- In `run_pipeline`, delete the `if settings.ingestion_source == "plaid"` / `else` branch (lines 51-56):
  always `fetch_accounts(owner_by_token)` + `upsert_plaid_accounts(accounts)`.

### 2b. Sample data seed script

**Create `scripts/seed_sample_data.py`**

Writes curated demo data **directly into Postgres via `DatabaseClient`** — no ingestion, no CSV file, no
Plaid credentials. This is the zero-credential demo path: `docker compose up -d` + this script + the
dashboard. It stays a deterministic *generator* (not a static SQL dump) because the dashboard shows the
trailing window relative to today — a static dump goes stale within weeks.

```
Usage: python scripts/seed_sample_data.py [--days 120]
Requires: DATABASE_URL only (via load_settings())
Seed: random.seed(42)  — deterministic across runs
```

**Flow:**
1. `load_settings()` → `DatabaseClient(settings.database_url)` → `ensure_schema()`.
2. Generate transactions (patterns below) into a DataFrame, tracking running balances.
3. `upsert_plaid_accounts(accounts)` — list-of-dicts, one per account in the table below, with
   `account_key=f"sample:{account_name}"`, `source="sample"`, `iso_currency_code="CAD"`, and
   `balance_current` = the final running balance after generation.
4. `upsert_categories(frame["category"].dropna().unique())` then `upsert_transactions(frame)` —
   `upsert_transactions` derives `account_key = "sample:{account_name}"` automatically from the
   `source`/`account_name` columns.

**Owners and accounts:**
| owner_name | account_name              | account_type | account_subtype |
|------------|---------------------------|--------------|-----------------|
| Alex       | Alex Chequing             | depository   | checking        |
| Alex       | Alex Rewards Visa         | credit       | credit card     |
| Alex       | Alex TFSA                 | investment   | tfsa            |
| Sam        | Sam Chequing              | depository   | checking        |
| Sam        | Sam High-Interest Savings | depository   | savings         |

**Sign convention**: positive amount = outflow (money leaving the account). This is the Plaid convention and is what `app/dashboard.py:387` assumes (`adjusted_amount = -amount`). State this clearly in the module docstring.

**Transaction patterns to generate** (each stamps a `category` — the placeholder ML can't categorize, so the
seed data must, or the Budget tab and category charts render empty. Names MUST match the Phase 3c canonical
title-case list):
- Biweekly payroll: `amount = -2800` (negative = inflow), `description = "Payroll - Direct Deposit"`, on the 1st and 15th of each month. Alex → Alex Chequing, Sam → Sam Chequing. Category `Income`.
- Monthly rent: `amount = 1350`, `description = "Rent"`, on the 1st, from Alex Chequing. Category `Housing`.
- Monthly utilities: `amount = 85`, `description = "Hydro - Utility Payment"`, on the 5th, from Sam Chequing. Category `Utilities`.
- Monthly Netflix: `amount = 17.99`, `description = "Netflix.com"`, on the 12th, from Alex Rewards Visa. Category `Subscriptions`.
- Monthly Spotify: `amount = 11.99`, `description = "Spotify Premium"`, on the 14th, from Sam Chequing. Category `Subscriptions`.
- Biweekly groceries: `amount = uniform(80, 220)`, `description` = random choice of `["Whole Foods Market", "IGA Supermarché", "Provigo"]`, 2-3x per month per owner. Category `Groceries`.
- Weekly restaurant/coffee: `amount = uniform(12, 65)`, `description` = random choice of `["Tim Hortons", "Starbucks Coffee", "Restaurant St-Denis", "Brasserie locale"]`, 1-2x per week per owner. Category `Dining`.
- Monthly transit: `amount = 100`, `description = "STM Opus Card"`, on the 2nd, from Sam Chequing. Category `Transport`.
- Weekly Uber: `amount = uniform(8, 35)`, `description = "Uber"`, 1x per week for Alex from Alex Rewards Visa. Category `Transport`.
- ATM withdrawals: `amount = choice([40, 60, 80, 100, 120])`, `description = "ATM Withdrawal"`, once or twice per month from chequing accounts. Category `ATM`.
- Monthly credit-card payment pair: On the 20th, post `amount = -350` to Alex Rewards Visa with `description = "Payment - Thank You"` AND `amount = 350` to Alex Chequing with `description = "Credit Card Payment"`. This exercises transfer-exclusion logic. Category `Transfer` (both rows).
- 3 anomaly purchases spread across 120 days: amounts of $450, $890, $1200, descriptions `"Electronics Store"`, `"Travel Agency"`, `"Appliance Purchase"`. Categories `Shopping`, `Travel`, `Shopping`.

**Outlier flags**: the 3 anomaly rows get `is_outlier = True`, `outlier_score = 0.9`; every other row gets
`is_outlier = False`, `outlier_score = 0.0`. (This is data the CSV path could never carry — it makes the
dashboard's anomaly section demo-able before ML activates.)

**Balance tracking**: maintain a running balance per account. Seed balances:
- Alex Chequing: 3500
- Alex Rewards Visa: 0 (credit — balance = amount owed, increases with purchases)
- Alex TFSA: 14000
- Sam Chequing: 4200
- Sam High-Interest Savings: 9800

After each transaction, update balance: `balance = prev_balance - amount` (for depository/investment); credit: `balance = prev_balance + amount` (positive purchases increase owed balance). Write current balance to `balance` column for each row. Sort by `date` ascending **before** computing balances.

**DataFrame columns** (what `upsert_transactions` consumes):
`date, description, amount, balance, account_name, source, transaction_id, category, outlier_score, is_outlier`
- `date`: `datetime.date` (ISO `YYYY-MM-DD` when stringified)
- `source`: literal `"sample"` on every row
- `transaction_id`: `f"SAMPLE-{i:05d}"` (zero-padded sequential, assigned after the date sort)

**Idempotency**: re-running on the same day is a no-op — `random.seed(42)` makes amounts identical, so
`build_transaction_hash` collides and `ON CONFLICT (transaction_hash) DO UPDATE` rewrites the same rows.
Re-running on a later day shifts the window and inserts the newly covered days. Note both behaviors in the
module docstring.

### 2c. `docker-compose.yml` (repo root)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: finance
      POSTGRES_PASSWORD: finance
      POSTGRES_DB: finance
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finance -d finance"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  pgdata:
```

No init SQL mount needed — `ensure_schema()` runs the migration DDL at runtime. Host port is 5433 (see the
5b note above) — inside the docker network/other containers it's still plain 5432.

**Security amendment (2.5f):** bind the published port to loopback so the demo Postgres (trivial
`finance/finance` creds) is never reachable from the network:
```yaml
    ports:
      - "127.0.0.1:5433:5432"  # loopback only — finance/finance is demo-grade, never front real data
```

---

## Phase 2.5 — Security hardening (code) — PUBLISH BLOCKER

> **Status (2026-07-18): 2.5a–2.5g implemented** — TLS enforcement (`core/config.py::enforce_tls`),
> `email_verified` check + dropped offline `access_type` (`core/google_oauth.py`), bounded/TTL'd OAuth
> pending-state store, generic user-facing errors with server-side logging (`app/streamlit_app.py`,
> `app/auth.py`), `psycopg.OperationalError` handling in `pipeline/runner.py::main`, loopback-bound
> `docker-compose.yml`, and masked Plaid token output in `scripts/create_sandbox_access_token.py`. Existing
> tests (`test_google_oauth.py`, `test_app_auth.py`) updated for the new `GoogleIdentity.email_verified`
> field and tuple-valued pending-session store; full suite passes. **2.5h is a docs-only decision**, still
> to be written up in the README (Phase 4a).
>
> **Update (2026-07-20): Phase 2.5 is now complete.** 2.5h landed with Phase 4 — the encryption-at-rest
> posture (managed-provider disk encryption + enforced TLS; application-level column encryption considered
> and deliberately rejected) is documented in the README's Security section. This clears Phase 2.5 as a
> publish blocker; the remaining blockers are the Phase 0 owner actions.

Findings from the 2026-07-07 security review of the live code. What is already sound and needs **no** work:
SQL is fully parameterized everywhere (`database/db.py` uses `%s`; dashboard filters are pandas-side — zero
injection surface); OAuth uses PKCE S256 + random `state` popped once; the email allowlist fails closed
(empty `GOOGLE_ALLOWED_EMAILS` → nobody signs in); data reads sit behind the auth gate; 4h session expiry;
no secrets in git history (verified via `git ls-files` + `git log --all`); Plaid tokens logged only by
6-char suffix; no `unsafe_allow_html`; no `st.cache_data` on financial data. Mobile sign-in needs no code
change — only the HTTPS redirect URI (Phase 0).

Implement after Phase 2 (the config/runner refactor must land first), before Phase 3.

### 2.5a. Enforce TLS on remote DB connections

`database/db.py:31,40` and `app/dashboard.py:180` pass the DSN through untouched — production
Supabase/Neon traffic is unencrypted unless the operator remembers `?sslmode=require`. Enforce it in code.

**File: `core/config.py`** — add a helper and apply it inside `load_settings()` so `DatabaseClient` and the
dashboard get it for free (no other file changes):

```python
from urllib.parse import parse_qs, urlsplit

_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1"}


def enforce_tls(database_url: str) -> str:
    """Append sslmode=require to remote DSNs that don't already specify an sslmode."""
    parts = urlsplit(database_url)
    host = (parts.hostname or "").lower()
    if host in _LOCAL_DB_HOSTS:
        return database_url
    if "sslmode" in parse_qs(parts.query):
        return database_url
    separator = "&" if parts.query else "?"
    return f"{database_url}{separator}sslmode=require"
```

In `load_settings()`: `database_url=enforce_tls(database_url)`. Localhost (docker demo) is exempt; an
explicit `sslmode` in the URL always wins (e.g. `sslmode=verify-full` is preserved, never downgraded).

### 2.5b. Require a verified email in the OAuth allowlist check

`core/google_oauth.py:78-101` authorizes purely on `email in allowed_emails` — the `email_verified` claim
is never read, so an unverified address could match the allowlist.

**File: `core/google_oauth.py`:**
- Add `email_verified: bool` to `GoogleIdentity`.
- In `fetch_userinfo`: `email_verified=payload.get("email_verified") in (True, "true")` (Google returns a
  bool in JSON but be tolerant of the string form).
- In `is_authorized_identity`: require `identity.email_verified` in addition to the allowlist match:
  ```python
  if not identity.email or not identity.email_verified:
      return False
  return identity.email in allowed_emails
  ```

### 2.5c. Stop requesting an unused Google refresh token

`build_authorization_url` (`core/google_oauth.py:44`) sends `access_type: "offline"`, so Google issues a
long-lived **refresh token** the app never uses — it sits in the discarded `token_response` after the one
userinfo call. Least-privilege: delete the `"access_type": "offline"` entry from the query dict. No other
change; the short-lived access token is all the flow needs.

### 2.5d. Harden the OAuth pending-state store

`app/auth.py:17` — `_google_oauth_pending_sessions: dict[str, str]` is module-global with no TTL or size
cap, and `render_sign_in` adds an entry on **every anonymous page view** (`start_google_sign_in` is called
unconditionally at `app/auth.py:133`), so any bot hitting the public URL grows it without bound, and stale
states stay valid forever. Note: the dict (not `st.session_state`) is the correct home — Streamlit session
state does **not** survive the OAuth redirect. Keep the design; bound it:

```python
_PENDING_TTL_SECONDS = 600
_PENDING_MAX_ENTRIES = 32
_google_oauth_pending_sessions: dict[str, tuple[str, float]] = {}  # state -> (verifier, created_at)


def _prune_pending_sessions(now: float) -> None:
    expired = [
        state
        for state, (_, created_at) in _google_oauth_pending_sessions.items()
        if now - created_at > _PENDING_TTL_SECONDS
    ]
    for state in expired:
        del _google_oauth_pending_sessions[state]
    while len(_google_oauth_pending_sessions) >= _PENDING_MAX_ENTRIES:
        oldest = min(_google_oauth_pending_sessions, key=lambda s: _google_oauth_pending_sessions[s][1])
        del _google_oauth_pending_sessions[oldest]
```

- `start_google_sign_in`: call `_prune_pending_sessions(time.time())`, then store
  `(code_verifier, time.time())`.
- `consume_google_callback`: unpack the tuple; reject (same "session expired" path) if the entry is older
  than `_PENDING_TTL_SECONDS`. Entries stay one-time-use via the existing `pop`.

### 2.5e. Error + information-disclosure hygiene

Internal details currently leak to the browser and to CI logs:

- **`app/streamlit_app.py:30-31`** — `st.error(f"Failed to load dashboard data: {error}")` renders raw
  psycopg errors (DSN host/port/user) into the browser. Replace with a generic
  `st.error("Failed to load dashboard data — check the server logs.")` + `LOGGER.exception(...)`
  server-side (add a module logger).
- **`app/auth.py:90`** — `st.error(f"Google sign-in failed: {error}")` → generic
  `st.error("Google sign-in failed. Please try again.")` + log the detail server-side.
- **`app/auth.py:141-143`** — the Supabase URL caption renders **before** the auth gate
  (`render_sidebar` runs at `streamlit_app.py:23`, sign-in at :25). Move the caption inside the
  `if st.session_state.get("authenticated_user"):` block (or drop it).
- **`pipeline/runner.py:70-74`** — `LOGGER.exception("Pipeline failed")` + bare `raise` dumps the full
  traceback (psycopg `OperationalError` embeds the DSN) into GitHub Actions logs. Replace `main()`'s
  handler:
  ```python
  try:
      run_pipeline()
  except psycopg.OperationalError as error:
      LOGGER.error("Pipeline failed: database connection error (%s)", type(error).__name__)
      raise SystemExit(1)
  except Exception:
      LOGGER.exception("Pipeline failed")
      raise
  ```
  (`SystemExit` keeps the job red without re-printing a DSN-bearing traceback; import `psycopg` in
  `runner.py`.)

### 2.5f. docker-compose loopback binding

Folded into 2c above: publish `"127.0.0.1:5433:5432"` with the demo-only comment.

### 2.5g. Mask the Plaid token in script output

`scripts/create_sandbox_access_token.py:115-118` prints the full access token to stdout (terminal history,
scrollback, screen shares). Change `main()`:
- Default output: `print(f"Created access_token: ...{access_token[-6:]}")` (suffix only).
- `--append` writes the full token to `.env` exactly as today (that file is the intended home, gitignored).
- Add an explicit `--print-token` flag for the manual-copy case (no `--append`); without it, instruct the
  user to re-run with `--append`.
- Print a reminder that `.env` now holds a live credential — if it is ever exposed, rotate via Phase 0.

### 2.5h. Encryption-at-rest posture (decision, no code)

Data at rest is protected by the managed provider's disk encryption (Supabase and Neon both encrypt at
rest); data in transit by enforced TLS (2.5a). **Application-level column encryption was considered and
deliberately rejected**: it breaks SQL-side aggregation the dashboard depends on, adds key management, and
buys nothing against the realistic threat model (a leaked DSN — which credential rotation covers).
Document this in the README Security section (Phase 4a) so the posture is explicit, not accidental.

---

## Phase 2.6 — UX fix: Google sign-in opens a second tab

**Problem** (found 2026-07-17): `render_sign_in()` in `app/auth.py:112-138` renders the sign-in link as
plain Markdown — `st.markdown(f"[Continue with Google]({auth_url})")` (line 134). Streamlit forces
`target="_blank"` (and strips any custom `target` attribute you try to set) on every link rendered through
`st.markdown`/`st.link_button` — a known, unfixable Streamlit limitation (see streamlit/streamlit issues
#3098, #4332, #7464, #11070). So clicking "Continue with Google" opens Google's consent screen in a *new*
tab; when Google redirects back to `redirect_uri`, that new tab becomes the signed-in app tab while the
original tab is left behind — the two-tabs annoyance.

**First attempt (2026-07-18, reverted — did not work)**: rendered the link via
`streamlit.components.v1.html(...)` using `<a href="..." target="_top">`. This made the button
*unresponsive* — clicking did nothing. Root cause, confirmed by reading the installed Streamlit frontend
bundle (`streamlit/static/static/js/IFrameUtil.BaqCY7QW.js`): `components.v1.html()` renders inside a
sandboxed `<iframe>` whose hardcoded sandbox attribute is
`allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts allow-downloads`
— it does **not** include `allow-top-navigation` / `allow-top-navigation-by-user-activation`, and
`components.html()` has no parameter to add them. Per the HTML sandbox spec, an iframe missing that flag
cannot navigate the top-level browsing context at all, by any means (click, script, form) — so
`target="_top"` inside it is silently blocked by the browser.

**Actual fix**: use `st.html()` instead (added in Streamlit 1.41.0). Its docstring states content is
**not** iframed — it renders straight into the main app DOM via DOMPurify. Confirmed via the installed
bundle (`streamlit/static/static/js/Html.xcp07OYh.js`) that its sanitizer only special-cases
`target="_blank"` (adds `rel="noopener noreferrer"`) and does not touch other `target` values, so
`target="_top"` passes through unmodified. Since the content isn't in an iframe to begin with, the click
navigates the tab directly.

### File: `app/auth.py`

1. Add import: `html` (stdlib, for escaping the URL into an attribute). No `streamlit.components.v1`
   import needed — `st.html` is a top-level Streamlit function.
2. Replace line 134:
   ```python
   st.markdown(f"[Continue with Google]({auth_url})")
   ```
   with:
   ```python
   safe_url = html.escape(auth_url)
   st.html(
       f'''
       <a href="{safe_url}" target="_top"
          style="display:inline-block;padding:0.5em 1em;background:#4285F4;color:white;
                 border-radius:4px;text-decoration:none;font-family:sans-serif;">
           Continue with Google
       </a>
       '''
   )
   ```
   Keep the existing `st.caption(...)` line below it as-is.

### File: `requirements.txt`
Bump `streamlit>=1.37.0` → `streamlit>=1.41.0` — `st.html` doesn't exist before that version.

No changes needed to `core/google_oauth.py` or `consume_google_callback` — the redirect URI and query-param
handling are unaffected; only how the *outbound* link is rendered changes.

### Verification
- `streamlit run app/streamlit_app.py`, load the sign-in page, confirm the "Continue with Google" button
  renders correctly (no iframe box/scrollbar artifact).
- Click it and confirm the browser navigates *within the same tab* to Google's consent screen (no new tab),
  and after granting consent, Google redirects back to the same tab and the dashboard loads signed in.
- Sign out and sign in again to confirm the flow is stable on repeat.

### Phase 2.6a — Amendment (2026-07-26): SCC's own hosting iframe reintroduces the same block — DONE, confirmed working live

> **Status (2026-07-26): confirmed fixed on the live deployment.** `target="_blank"` shipped
> (`e664078`/`9f0b34d`, merged to `main`), and sign-in was verified end-to-end on the live SCC URL with
> `jacosse1@gmail.com` on desktop — a real request to `accounts.google.com` now fires, the new tab
> completes sign-in, and the dashboard renders with correct transaction data. **Confirmed 2026-07-27** for
> the second allowlisted account (`lapointe.alexie@gmail.com`) too. **Not yet verified:** mobile sign-in —
> still open, tracked in Phase 10i.

**Problem found after deploying to Streamlit Community Cloud (SCC):** the sign-in button, which passed
every check above, was a completely dead link on the live SCC deployment — clicking it produced no error,
no console warning, and (confirmed via the Network tab) no request to Google at all. Every Google-side
config was checked and correct (Client ID, Application type, Authorized redirect URIs, Test users,
`GOOGLE_ALLOWED_EMAILS`, project consistency, an SCC reboot) — none of it mattered, because the click never
got that far.

**Root cause, confirmed by inspecting the live DOM:** SCC wraps every hosted app in its own outer iframe for
platform chrome:

```html
<iframe sandbox="allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox
                 allow-same-origin allow-scripts allow-downloads" ...>
```

Same missing flag as the original Phase 2.6 problem — no `allow-top-navigation` /
`allow-top-navigation-by-user-activation` — but this is a *different* iframe. `st.html()`'s fix above is
still correct: its content genuinely isn't iframed by Streamlit itself. SCC's hosting layer adds its own
wrapper around the **entire app**, one level higher, with the identical restrictive sandbox — something
that cannot exist under local `streamlit run`, so nothing in the verification above could ever have caught
it. Copy-pasting the link's `href` directly into a new tab's address bar worked perfectly, confirming the
URL itself was never the problem — only navigating to it from inside SCC's iframe was blocked.

**Fix:** `app/auth.py`'s anchor `target` changed from `"_top"` to `"_blank"` — the one mechanism this
sandbox leaves open (`allow-popups` + `allow-popups-to-escape-sandbox` are both granted). Guarded by a new
test, `tests/test_app_auth.py::test_sign_in_link_opens_in_new_tab`, since this exact attribute has now been
the crux of two separate bugs and a silent regression produces a dead button with zero error output.

**Accepted trade-off (not SCC-only):** `target="_top"` on a page with no parent frame — local `streamlit
run` — is equivalent to same-tab navigation, so this change makes sign-in open a new tab **everywhere**,
not just on SCC. The alternative (a script that opens a new tab only when actually framed) depends on
inline `<script>` content surviving `st.html()`'s DOMPurify sanitization, which is unconfirmed and risks
silently reproducing this same failure mode if it doesn't survive — the simple, unconditional fix was
chosen deliberately over that risk.

---

## Phase 2.7 — Implemented (2026-07-17): account identity + post-rotation dedup

**This phase documents work already shipped on `dev`**, done in response to the Phase 0 credential rotation
— it wasn't planned ahead of time, but changes assumptions the rest of this plan makes, so it's recorded
here rather than left undocumented.

**Problem discovered during rotation**: re-issuing the Plaid access tokens re-links each Item, and Plaid
mints a *new* `account_id` for every account on re-link — even though it's the same physical account. Since
`account_key` was derived from `account_id`, this produced a second `accounts` row per real account, with
its own parallel transaction history split off from the original.

**What shipped:**
- **`database/migrations/004_account_identity.sql`** — adds `persistent_account_id` (Plaid's stable
  cross-relink identifier) and `mask` to `accounts`, with a unique index on `persistent_account_id`.
- **`ingestion/plaid_ingestor.py`** — now captures `persistent_account_id` and `mask` from Plaid and folds
  the mask into the display name (`"{name} (••••{mask})"`).
- **`database/db.py`**:
  - `build_transaction_hash` now hashes `account_key|date|description|amount` instead of
    `account_name|date|description|amount` — `account_name` could collide across owners/accounts, and the
    hash needed to key off something durable.
  - New `merge_account(duplicate_key, canonical_key)` — reassigns a duplicate account's transactions onto
    the canonical account_key, then deletes the duplicate `accounts` row.
  - New `rehash_transactions()` — recomputes every row's `transaction_hash` under the new formula and
    dedupes any rows that collide as a result (keeps the earliest row).
- **`scripts/dedupe_accounts.py`** (new, one-off/on-demand) — groups existing accounts by
  `persistent_account_id`, falling back to a `(mask, official_name, account_subtype, owner_name)` heuristic
  for pre-`persistent_account_id` rows; merges each duplicate group via `merge_account`, then calls
  `rehash_transactions()`. Dry-run by default; `--apply` performs the writes.

**Status**: fully implemented and already run against production (`--apply`) as part of the 2026-07-17
Plaid secret rotation (Phase 0).

**Amendment to "Ordering constraints / risks" item 8** (below): the original rule — "never change
`build_transaction_hash` inputs" — is superseded. This was the one sanctioned exception, and it shipped
together with `rehash_transactions()` specifically so existing rows could migrate safely. Any *future*
change to the hash inputs must ship the same way: a `DatabaseClient` method that recomputes and dedupes
every existing row, never a silent formula swap.

---

## Phase 2.8 — Implemented (2026-07-19): transaction_hash type-independence fix

**This phase documents work already shipped**, fixing a second, distinct duplication bug uncovered after
Phase 2.7 landed: transactions kept duplicating on every pipeline run, even though accounts were already
correctly merged. Root cause: `build_transaction_hash` (`database/db.py`) stringified `amount`/`date` with
a bare `str()`. `upsert_transactions` feeds it a pipeline `float` (`str(100.0) == "100.0"`);
`rehash_transactions` feeds it a Postgres `Decimal` read back from the `NUMERIC(12,2)` column
(`str(Decimal("100.00")) == "100.00"`) — different strings, different hashes, for the *same* transaction.
Since `dedupe_accounts.py --apply` ends with `rehash_transactions()`, every account-rotation cleanup left
`transaction_hash` in the Decimal form; the next `python main.py` run then computed the float form for the
same rows, found no `ON CONFLICT` match, and inserted an exact duplicate (differing only in
`transaction_hash` and `created_at` — matching the reported symptom exactly).

**What shipped:**
- **`database/db.py`** — `build_transaction_hash` now routes `amount` through `_canonical_amount()`
  (`Decimal(str(value)).quantize(Decimal("0.01"))`) and `date` through `_canonical_date()` (handles
  `datetime.date`, `datetime.datetime`/`pd.Timestamp`, and ISO-ish strings uniformly), so the hash is
  identical regardless of which call site's Python types produced it. This is the **second** sanctioned
  change to the hash formula under the Phase 2.7 amendment above.
- **`database/migrations/005_transaction_natural_key.sql`** — `CREATE UNIQUE INDEX
  transactions_natural_key ON transactions (account_key, transaction_date, description, amount)`. Defence
  in depth: Postgres now compares the natural key directly (`NUMERIC` to `NUMERIC`), so any *future*
  hash-formatting drift raises a loud unique-violation instead of silently duplicating rows again.
- **`tests/test_db_hash.py`** — added type-independence tests (`amount` as float/Decimal/int/str, `date` as
  date/datetime/Timestamp/str) covering the exact values that diverged in production (`100`, `-2800`,
  `12.5`), plus a differencing regression guard so canonicalization doesn't collapse genuinely distinct
  transactions.
- **`scripts/dedupe_accounts.py`** — added `--rehash-only`, which skips account grouping and calls
  `database.rehash_transactions()` directly; the plain `--apply` path short-circuits on "no duplicate
  accounts found" and never reaches the rehash once accounts are already clean, so this is now the correct
  entry point for a hash-formula-only fix.

No changes to `analytics/`, `app/dashboard.py`, or the ingestion layer — this was isolated to the hash
formula and its DB-level backstop.

**Status**: fully implemented — production cleanup (`python scripts/dedupe_accounts.py --rehash-only`) was
run 2026-07-20, clearing pre-existing hash-formula duplicates before migration 005's unique index took
effect. No further action needed for this phase.

---

## Phase 3 — Dashboard improvements

Implement the steps in the lettered order below. They build on each other. Do not skip ahead.

> **Status (2026-07-17): 3a–3n implemented on `dev`**, in `feat(dashboard): add tabs and overal better ux`
> (commit `14072e9`). Verified against the code: `_classify_tx_type` (3a), the four new `DatabaseClient`
> methods (3b), migrations 002/003 (3c), `ensure_schema` iterating all migration files (3d), the
> `COALESCE(user_category, category)` + `transaction_hash` SELECT (3e), `render_dashboard(tx_df, acct_df,
> database_url)` (3f), `_enrich_transactions` with the dead `return df` removed (3g), all four new
> `_STRINGS` keys present in both `en`/`fr` (3h), `_section_overview` (3i), the savings-rate metric and
> income-vs-expenses mom-bar addition in `_section_cash_flow` (3j), `_section_budget` (3k), inline category
> editing in `_section_ledger` via the
> `edited_rows` pattern (3l), anomalies inside the Transactions tab (3m), and the final tabbed
> `render_dashboard` layout (3n) all match this plan's spec closely. **Update (2026-07-20): 3o, 3p, 3q, and
> 3r are now all implemented** — see each section below for specifics (3q shipped its migration as `006_`,
> not `005_`, since Phase 2.8 had already claimed `005_`). Phase 3 is complete.

### 3a. Fix `_classify_tx_type` in `app/dashboard.py`

> **Superseded by Phase 3r** (below): the `_classify_tx_type` body shown here is no longer what ships —
> credit-account refunds now net into `expense` instead of `income`, and a paired-transfer override was added.
> See Phase 3r for the current rules.

**Current problem** (line 194-208): NULL/unknown `account_type` defaults everything to "expense", including payroll deposits — income and net cash flow are wrong.

**Replace** lines 194-208 with:

```python
_PAYMENT_KEYWORDS = r"payment|paiement|prélèvement|prelevement|transfer|xfer"
_REFUND_KEYWORDS  = r"cashback|cash.?back|remise|refund|rebate|return"


def _classify_tx_type(df: pd.DataFrame) -> pd.Series:
    """Classify each row as 'income', 'expense', or 'transfer'.

    Sign convention (Plaid): positive amount = outflow; negative = inflow.
    adjusted_amount = -amount, so positive adjusted_amount = income/gain.
    """
    types = pd.Series("expense", index=df.index)

    is_depository_or_investment = df["account_type"].isin(["depository", "investment"])
    is_credit = df["account_type"] == "credit"
    is_unknown = ~is_depository_or_investment & ~is_credit  # NULL or unrecognized

    # Depository / investment: negative amount = money arriving = income
    types[is_depository_or_investment & (df["amount"] < 0)] = "income"
    # Depository / investment: positive amount with payment keyword = transfer
    types[
        is_depository_or_investment
        & (df["amount"] > 0)
        & df["description"].str.contains(_PAYMENT_KEYWORDS, case=False, na=False)
    ] = "transfer"

    # Credit card: positive = purchase = expense (default already set)
    # Credit card: negative + refund keyword = cashback/rebate = income
    types[
        is_credit
        & (df["amount"] < 0)
        & df["description"].str.contains(_REFUND_KEYWORDS, case=False, na=False)
    ] = "income"
    # Credit card: negative without refund keyword = payment received = transfer
    types[
        is_credit
        & (df["amount"] < 0)
        & ~df["description"].str.contains(_REFUND_KEYWORDS, case=False, na=False)
    ] = "transfer"

    # Unknown account_type: treat negative amounts as income (conservative fallback)
    types[is_unknown & (df["amount"] < 0)] = "income"

    return types
```

### 3b. New DB methods in `database/db.py`

**First**, add these imports at the top of `database/db.py` if not already present — they are used in the new methods:
```python
import pathlib  # already used in ensure_schema after 3d; add now
```

Add four new methods to `DatabaseClient` **before** `upsert_categories`:

```python
def get_categories(self) -> list[str]:
    """Return all category names from the categories table, sorted."""
    sql = "SELECT name FROM categories ORDER BY name"
    with psycopg.connect(self.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [r[0] for r in rows]

def get_budgets(self) -> list[dict]:
    """Return all budget rows as a list of dicts: {category, monthly_limit}."""
    sql = "SELECT category, monthly_limit::double precision FROM budgets ORDER BY category"
    with psycopg.connect(self.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [{"category": r[0], "monthly_limit": r[1]} for r in rows]

def upsert_budget(self, category: str, monthly_limit: float) -> None:
    """Insert or update a budget row."""
    sql = """
    INSERT INTO budgets (category, monthly_limit)
    VALUES (%s, %s)
    ON CONFLICT (category) DO UPDATE
    SET monthly_limit = EXCLUDED.monthly_limit,
        updated_at    = NOW()
    """
    self._execute_many(sql, [(category, monthly_limit)])

def update_transaction_category(self, transaction_hash: str, category: str) -> None:
    """Set user_category for a transaction (survives pipeline re-runs).
    Also inserts the category into the categories table so it appears in future dropdowns.
    """
    with psycopg.connect(self.database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO categories (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                (category,)
            )
            cur.execute(
                "UPDATE transactions SET user_category = %s, updated_at = NOW() WHERE transaction_hash = %s",
                (category, transaction_hash)
            )
        conn.commit()
```

**Why `update_transaction_category` writes `user_category` (not `category`)**: The pipeline's `upsert_transactions` does `ON CONFLICT (transaction_hash) DO UPDATE SET category = EXCLUDED.category`. If manual edits wrote to `category`, every pipeline run would overwrite them silently. Instead, the dashboard writes to `user_category`, which the pipeline never touches. The SELECT query (3e) reads `COALESCE(user_category, category)` so the effective category is always the user's override when set, falling back to ML output.

### 3c. New migrations

#### `database/migrations/002_budgets.sql`

```sql
CREATE TABLE IF NOT EXISTS budgets (
    id             BIGSERIAL PRIMARY KEY,
    category       TEXT NOT NULL UNIQUE,
    monthly_limit  NUMERIC(12, 2) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

#### `database/migrations/003_user_category.sql`

Two things: add the `user_category` column to `transactions`, and seed the `categories` table with a canonical set so the dropdown is immediately useful (before ML activates).

```sql
-- Add manual-override category column; pipeline never writes this column
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_category TEXT;

-- Seed canonical personal-finance categories
INSERT INTO categories (name) VALUES
    ('ATM'),
    ('Dining'),
    ('Entertainment'),
    ('Groceries'),
    ('Health'),
    ('Housing'),
    ('Income'),
    ('Savings'),
    ('Shopping'),
    ('Subscriptions'),
    ('Transfer'),
    ('Transport'),
    ('Travel'),
    ('Uncategorized'),
    ('Utilities')
ON CONFLICT (name) DO NOTHING;
```

**Note on case**: use title case consistently. The existing pipeline stamps `"uncategorized"` (lowercase); add both forms or normalise. Recommended: add `ON CONFLICT (name) DO NOTHING` keeps the existing lowercase `"uncategorized"` row and also adds the seed `"Uncategorized"` — since `categories.name` has a case-sensitive unique constraint, both exist. To avoid this duplication, either: (a) update the placeholder in `analytics/placeholders.py` to stamp `"Uncategorized"` (title case), or (b) use lowercase throughout in the seed. Choose **title case everywhere** — update `analytics/placeholders.py` line that sets `category = "uncategorized"` to `category = "Uncategorized"` as part of this step.

### 3d. `database/db.py` — `ensure_schema()`: iterate all migrations

Replace `ensure_schema` (lines 36-43) with a version that runs all `*.sql` files in `database/migrations/` sorted lexicographically:

```python
def ensure_schema(self) -> None:
    import pathlib
    migrations_dir = pathlib.Path("database/migrations")
    sql_files = sorted(migrations_dir.glob("*.sql"))
    with psycopg.connect(self.database_url) as connection:
        with connection.cursor() as cursor:
            for sql_file in sql_files:
                cursor.execute(sql_file.read_text(encoding="utf-8"))
        connection.commit()
```

This runs 001, 002, 003 in order. Each is idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).

### 3e. Update `load_financial_data` SELECT query in `app/dashboard.py`

**Add these two imports** at the top of `app/dashboard.py` (after existing imports):
```python
import calendar
from database.db import DatabaseClient
```

`timedelta` is already available from the standard library — add `from datetime import date, timedelta` if it is not already imported.

Update `tx_query` (lines 152-167) to:
1. Include `t.transaction_hash` (needed by the ledger editor).
2. Use `COALESCE(t.user_category, t.category) AS category` so manual overrides take precedence over ML output.

```sql
SELECT
    t.transaction_date   AS date,
    t.transaction_hash,
    a.account_name,
    a.owner_name,
    a.account_type,
    a.account_subtype,
    t.description,
    t.amount::double precision AS amount,
    COALESCE(t.user_category, t.category) AS category,
    t.outlier_score,
    t.is_outlier
FROM transactions t
JOIN accounts a ON t.account_key = a.account_key
ORDER BY t.transaction_date DESC
```

### 3f. Add `database_url` parameter to `render_dashboard`

Change the function signature (line 542):
```python
def render_dashboard(tx_df: pd.DataFrame, acct_df: pd.DataFrame, database_url: str) -> None:
```

In `app/streamlit_app.py` (line 34):
```python
render_dashboard(tx_data, acct_data, settings.database_url)
```

`database_url` is passed down only to `_section_budget` and `_section_ledger`.

### 3g. Add `_enrich_transactions(df)` helper and remove `return df`

Add this function **before** `_section_cash_flow`:

```python
def _enrich_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Add adjusted_amount, month, and tx_type columns. Call once before tabs."""
    df = df.copy()
    df["adjusted_amount"] = -df["amount"]
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df["tx_type"] = _classify_tx_type(df)
    return df
```

In `_section_cash_flow`:
- **Remove** these three lines (they are now in `_enrich_transactions`):
  ```python
  df["adjusted_amount"] = -df["amount"]
  df["month"] = df["date"].dt.to_period("M").astype(str)
  df["tx_type"] = _classify_tx_type(df)
  ```
- **Remove** the `return df` statement at the end of the function (line 467) — it is dead code after this refactor.
- Keep `df = df.copy()` at the start of `_section_cash_flow` to avoid mutating the caller's frame.

### 3h. Add new string keys to `_STRINGS` (both "en" and "fr")

Add the following keys to **both** language dicts. Do not remove existing keys.

**EN additions:**
```python
# Tabs
"tab_overview":              "Overview",
"tab_cashflow":              "Cash flow",
"tab_budget":                "Budget",
"tab_transactions":          "Transactions",
# Overview section
"s0_heading":                "Summary",
"metric_savings_rate":       "Savings rate",
"chart_top_categories":      "Top spending categories",
"chart_mom_comparison":      "Month-over-month by category",
"label_this_month":          "This month",
"label_last_month":          "Last month",
"chart_income_breakdown":    "Income sources",
"chart_savings_rate_trend":  "Monthly savings rate (%)",
"metric_emergency_fund":     "Emergency fund coverage",
"emergency_fund_months":     "{months:.1f} months of expenses covered",
"emergency_fund_note":       "Liquid savings ÷ average monthly expenses.",
# Budget section
"s_budget_heading":          "Budget",
"s_budget_caption":          "Monthly spending limits by category.",
"budget_col_category":       "Category",
"budget_col_limit":          "Limit ($)",
"budget_col_spent":          "Spent",
"budget_col_projected":      "Projected EOM",
"budget_col_actual":         "Actual",
"budget_edit_label":         "Edit budget limits",
"budget_save":               "Save budgets",
"budget_saved":              "Budgets saved.",
"budget_over":               "Over budget",
"budget_on_track":           "On track",
"budget_current_month_note": "Budget view follows your period filter. Projection only shown for current month.",
# Cash flow additions
"chart_mom_bar":             "Income vs. expenses by month",
"chart_savings_rate":        "Monthly savings rate (%)",
# Transactions tab
"edit_cat_label":            "Edit categories inline — changes persist across pipeline re-runs.",
```

**FR additions:**
```python
"tab_overview":              "Aperçu",
"tab_cashflow":              "Flux monétaires",
"tab_budget":                "Budget",
"tab_transactions":          "Transactions",
"s0_heading":                "Résumé",
"metric_savings_rate":       "Taux d'épargne",
"chart_top_categories":      "Principales catégories de dépenses",
"chart_mom_comparison":      "Comparaison mois par mois par catégorie",
"label_this_month":          "Ce mois",
"label_last_month":          "Mois dernier",
"chart_income_breakdown":    "Sources de revenus",
"chart_savings_rate_trend":  "Taux d'épargne mensuel (%)",
"metric_emergency_fund":     "Fonds d'urgence",
"emergency_fund_months":     "{months:.1f} mois de dépenses couverts",
"emergency_fund_note":       "Épargne liquide ÷ dépenses mensuelles moyennes.",
"s_budget_heading":          "Budget",
"s_budget_caption":          "Limites de dépenses mensuelles par catégorie.",
"budget_col_category":       "Catégorie",
"budget_col_limit":          "Limite ($)",
"budget_col_spent":          "Dépensé",
"budget_col_projected":      "Prévision fin de mois",
"budget_col_actual":         "Réel final",
"budget_edit_label":         "Modifier les limites budgétaires",
"budget_save":               "Enregistrer",
"budget_saved":              "Budgets enregistrés.",
"budget_over":               "Dépassé",
"budget_on_track":           "Dans les limites",
"budget_current_month_note": "La vue budget suit le filtre de période. La projection n'est affichée que pour le mois en cours.",
"chart_mom_bar":             "Revenus vs. dépenses par mois",
"chart_savings_rate":        "Taux d'épargne mensuel (%)",
"edit_cat_label":            "Modifiez les catégories en ligne — les changements survivent aux ré-exécutions du pipeline.",
```

### 3i. New `_section_overview` function

Add **after** `_build_sidebar_filters` and **before** `_section_cash_flow`.

```python
def _section_overview(
    df: pd.DataFrame,
    acct_df: pd.DataFrame,
    T: dict[str, str],
    lang: str,
    selected_owners: list[str],
) -> None:
    st.subheader(T["s0_heading"])
```

**Row 1 — 5 KPI metrics:**
```python
real = df[df["tx_type"] != "transfer"]
income    = real[real["tx_type"] == "income"]["adjusted_amount"].sum()
expenses  = real[real["tx_type"] == "expense"]["adjusted_amount"].sum().abs()
net_flow  = income - expenses
savings_rate = (net_flow / income * 100) if income > 0 else 0.0
flagged   = int(df["is_outlier"].sum())

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(T["metric_income"],   f"+${income:,.2f}")
m2.metric(T["metric_expenses"], f"-${expenses:,.2f}")
m3.metric(T["metric_net_flow"], f"${net_flow:,.2f}",
          delta=f"${net_flow:,.2f}",
          delta_color="normal" if net_flow >= 0 else "inverse")
m4.metric(T["metric_savings_rate"], f"{savings_rate:.1f}%")
m5.metric(T["metric_flags"], str(flagged))
```

**Row 2 — 2-column chart row:**

Left — Top spending categories (horizontal bar, top 10, sorted ascending so largest is at top):
```python
top_cats = (
    df[df["tx_type"] == "expense"]
    .groupby("category", as_index=False)["adjusted_amount"]
    .sum()
    .assign(abs_amount=lambda x: x["adjusted_amount"].abs())
    .nlargest(10, "abs_amount")
    .sort_values("abs_amount")
)
fig = px.bar(top_cats, x="abs_amount", y="category", orientation="h",
             title=T["chart_top_categories"],
             labels={"abs_amount": T["axis_amount"], "category": T["col_cat"]},
             template="plotly_white")
st.plotly_chart(fig, use_container_width=True)
```

Right — Month-over-month comparison (two most recent months in the filtered data):
```python
months_sorted = sorted(df["month"].unique())
if len(months_sorted) >= 2:
    this_m, last_m = months_sorted[-1], months_sorted[-2]
    mom = df[df["month"].isin([this_m, last_m]) & (df["tx_type"] == "expense")]
    mom_grp = mom.groupby(["category", "month"], as_index=False)["adjusted_amount"].sum()
    mom_grp["abs_amount"] = mom_grp["adjusted_amount"].abs()
    mom_grp["period"] = mom_grp["month"].map(
        {this_m: T["label_this_month"], last_m: T["label_last_month"]}
    )
    fig2 = px.bar(mom_grp, x="category", y="abs_amount", color="period",
                  barmode="group", title=T["chart_mom_comparison"], template="plotly_white")
    st.plotly_chart(fig2, use_container_width=True)
```

**Row 3 — Emergency fund indicator:**
```python
owner_mask = (
    acct_df["owner_name"].isin(selected_owners)
    if selected_owners
    else pd.Series(True, index=acct_df.index)
)
liquid_assets = acct_df[
    acct_df["account_type"].isin(["depository"]) & owner_mask
]["balance_current"].sum()

monthly_expenses_series = (
    df[df["tx_type"] == "expense"]
    .groupby("month")["adjusted_amount"]
    .sum()
    .abs()
)
if not monthly_expenses_series.empty:
    avg_monthly_expenses = monthly_expenses_series.mean()
    if avg_monthly_expenses > 0:
        months_covered = liquid_assets / avg_monthly_expenses
        st.metric(T["metric_emergency_fund"],
                  T["emergency_fund_months"].format(months=months_covered))
        st.caption(T["emergency_fund_note"])
        st.progress(min(months_covered / 6, 1.0))
```

**Row 4 — Income breakdown and savings rate trend (side by side):**
```python
c1, c2 = st.columns(2)
with c1:
    income_src = (
        df[df["tx_type"] == "income"]
        .groupby("description", as_index=False)["adjusted_amount"]
        .sum()
        .nlargest(8, "adjusted_amount")
    )
    if not income_src.empty:
        fig_inc = px.pie(income_src, values="adjusted_amount", names="description",
                         title=T["chart_income_breakdown"], hole=0.35, template="plotly_white")
        st.plotly_chart(fig_inc, use_container_width=True)

with c2:
    monthly = (
        df[df["tx_type"] != "transfer"]
        .groupby("month")
        .apply(lambda g: pd.Series({
            "income":   g.loc[g["tx_type"] == "income",   "adjusted_amount"].sum(),
            "expenses": g.loc[g["tx_type"] == "expense",  "adjusted_amount"].sum().abs(),
        }))
        .reset_index()
    )
    monthly["savings_rate"] = (
        (monthly["income"] - monthly["expenses"])
        / monthly["income"].clip(lower=0.01) * 100
    )
    fig_sr = px.line(monthly, x="month", y="savings_rate",
                     title=T["chart_savings_rate_trend"],
                     labels={"savings_rate": "%", "month": T["axis_month"]},
                     template="plotly_white")
    fig_sr.add_hline(y=20, line_dash="dot", line_color="green",
                     annotation_text="Target 20%")
    st.plotly_chart(fig_sr, use_container_width=True)
```

### 3j. Improve `_section_cash_flow`

Make these targeted additions to the existing function (do not rewrite entirely):

1. **Add savings rate metric** — change `m1, m2, m3, m4, m5 = st.columns(5)` to `m1, m2, m3, m4, m5, m6 = st.columns(6)` and append:
   ```python
   savings_rate = (net_flow / income * 100) if income > 0 else 0.0
   m6.metric(T["metric_savings_rate"], f"{savings_rate:.1f}%")
   ```

2. **Add full-width income vs. expenses grouped bar** before the existing two-column chart pair:
   ```python
   mom_summary = (
       df[df["tx_type"] != "transfer"]
       .groupby(["month", "tx_type"], as_index=False)["adjusted_amount"]
       .sum()
   )
   mom_summary.loc[mom_summary["tx_type"] == "expense", "adjusted_amount"] = (
       mom_summary.loc[mom_summary["tx_type"] == "expense", "adjusted_amount"].abs()
   )
   fig_mom = px.bar(mom_summary, x="month", y="adjusted_amount", color="tx_type",
                    barmode="group", title=T["chart_mom_bar"], template="plotly_white",
                    labels={"adjusted_amount": T["axis_amount"], "month": T["axis_month"]})
   st.plotly_chart(fig_mom, use_container_width=True)
   ```

3. Keep the existing rolling 30-day burn (left) and monthly net by holder (right) as the second row.
4. Keep the category distribution stacked bar at the bottom.

### 3k. New `_section_budget` function

Add after `_section_cash_flow`. Signature: `(df, T, database_url)`.

**Important design decisions baked in:**
- Budget limits are **global** (one limit per category, applies to all months).
- The view **follows the sidebar period filter**: shows spending for whatever month is selected.
- "Projected EOM" is shown only when the selected period includes the **current calendar month**; otherwise it shows "Actual final spend".

```python
def _section_budget(df: pd.DataFrame, T: dict[str, str], database_url: str) -> None:
    import calendar
    from datetime import date

    st.subheader(T["s_budget_heading"])
    st.caption(T["s_budget_caption"])
    st.caption(T["budget_current_month_note"])

    db = DatabaseClient(database_url)
    budget_rows = db.get_budgets()
    budget_map = {r["category"]: r["monthly_limit"] for r in budget_rows}

    # Determine the period in the filtered data
    current_month_str = df["month"].max()  # e.g. "2025-03"
    today = date.today()
    today_month_str = today.strftime("%Y-%m")
    is_current_month = current_month_str == today_month_str

    # Compute spending for the selected period
    period_expenses = (
        df[(df["month"] == current_month_str) & (df["tx_type"] == "expense")]
        .groupby("category")["adjusted_amount"]
        .sum()
        .abs()
        .to_dict()
    )

    # Projection factor — only meaningful for the current calendar month
    if is_current_month:
        days_in_month = calendar.monthrange(today.year, today.month)[1]
        days_elapsed = max(today.day, 1)
        projection_factor = days_in_month / days_elapsed
    else:
        projection_factor = None  # historical — show actual, not projection

    # Categories to show: any category with spending OR with a budget set
    all_categories = sorted(
        set(period_expenses.keys()) | set(budget_map.keys())
    )

    for cat in all_categories:
        spent = period_expenses.get(cat, 0.0)
        limit = budget_map.get(cat)

        if is_current_month and projection_factor is not None:
            projected_label = f"Projected EOM: ${spent * projection_factor:,.2f}"
        else:
            projected_label = f"Actual: ${spent:,.2f}"

        if limit:
            pct = min(spent / limit, 1.0)
            status = T["budget_over"] if spent > limit else T["budget_on_track"]
            label = f"{cat} — ${spent:,.2f} / ${limit:,.2f} ({pct*100:.0f}%) — {status} | {projected_label}"
            st.progress(pct, text=label)
        else:
            st.write(f"**{cat}**: ${spent:,.2f} spent (no budget set) | {projected_label}")

    st.divider()
    st.markdown(f"**{T['budget_edit_label']}**")

    # Budget editor — all canonical categories from DB
    all_edit_cats = db.get_categories()
    editor_df = pd.DataFrame([
        {"category": cat, "monthly_limit": budget_map.get(cat, 0.0)}
        for cat in all_edit_cats
    ])
    edited = st.data_editor(
        editor_df,
        key="budget_editor",
        column_config={
            "category":      st.column_config.TextColumn(T["budget_col_category"], disabled=True),
            "monthly_limit": st.column_config.NumberColumn(
                T["budget_col_limit"], min_value=0, format="$%.2f"
            ),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
    )
    if st.button(T["budget_save"]):
        for _, row in edited.iterrows():
            if row["monthly_limit"] > 0:
                db.upsert_budget(str(row["category"]), float(row["monthly_limit"]))
        st.success(T["budget_saved"])
        st.rerun()
```

### 3l. Update `_section_ledger` — inline category editing

Replace the current `_section_ledger` (lines 517-539).

**Design**: use `st.data_editor`'s `key` parameter and read `st.session_state[key]["edited_rows"]` to detect only cells the user actually changed — this prevents spurious DB writes on every Streamlit rerun caused by unrelated widget interactions.

```python
def _section_ledger(df: pd.DataFrame, T: dict[str, str], database_url: str) -> None:
    st.subheader(T["s5_heading"])
    st.caption(T["s5_caption"])
    st.caption(T["edit_cat_label"])

    db = DatabaseClient(database_url)
    all_cats = db.get_categories()  # canonical list from categories table

    display = df[[
        "transaction_hash", "date", "owner_name", "account_name",
        "description", "adjusted_amount", "category"
    ]].copy()
    display.columns = [
        "hash",
        T["col_date"], T["col_owner"], T["col_account"],
        T["col_desc"], T["col_amount"], T["col_cat"],
    ]

    editor_key = "ledger_editor"
    st.data_editor(
        display,
        key=editor_key,
        column_config={
            "hash": None,  # hidden
            T["col_cat"]: st.column_config.SelectboxColumn(
                T["col_cat"], options=all_cats, required=False
            ),
        },
        disabled=[
            T["col_date"], T["col_owner"], T["col_account"],
            T["col_desc"], T["col_amount"],
        ],
        use_container_width=True,
        hide_index=True,
    )

    # Only act on rows the user actually changed this render cycle
    editor_state = st.session_state.get(editor_key, {})
    for row_idx_str, col_changes in editor_state.get("edited_rows", {}).items():
        if T["col_cat"] in col_changes:
            row_idx = int(row_idx_str)
            new_cat = col_changes[T["col_cat"]]
            if new_cat:
                transaction_hash = display.iloc[row_idx]["hash"]
                db.update_transaction_category(str(transaction_hash), str(new_cat))
```

### 3m. `_section_anomalies` — move to Transactions tab

No content change to `_section_anomalies` itself. It is called inside the Transactions tab in 3n.

### 3n. Rewrite `render_dashboard` — tab layout

Replace the body of `render_dashboard` (lines 558-585) with:

```python
def render_dashboard(tx_df: pd.DataFrame, acct_df: pd.DataFrame, database_url: str) -> None:
    def _on_lang_toggle() -> None:
        st.session_state["lang"] = "fr" if st.session_state.get("lang_fr") else "en"

    st.sidebar.toggle(
        "Français", key="lang_fr",
        value=st.session_state.get("lang", "en") == "fr",
        on_change=_on_lang_toggle,
    )
    st.sidebar.divider()

    lang = st.session_state.get("lang", "en")
    T = _STRINGS[lang]

    st.title(T["title"])

    if tx_df.empty and acct_df.empty:
        st.info(T["no_data"])
        return

    if tx_df.empty:
        st.info(T["no_transactions"])
        _section_net_worth(acct_df, T, lang, [])
        return

    tx = tx_df.copy()
    tx["date"] = pd.to_datetime(tx["date"])

    filtered, selected_owners = _build_sidebar_filters(tx, T)

    if filtered.empty:
        st.info(T["no_transactions"])
        return

    # Enrich once so all tabs share adjusted_amount / month / tx_type
    enriched = _enrich_transactions(filtered)

    tab_overview, tab_cashflow, tab_budget, tab_transactions = st.tabs([
        T["tab_overview"], T["tab_cashflow"], T["tab_budget"], T["tab_transactions"]
    ])

    with tab_overview:
        _section_net_worth(acct_df, T, lang, selected_owners)
        st.divider()
        _section_overview(enriched, acct_df, T, lang, selected_owners)

    with tab_cashflow:
        _section_cash_flow(enriched, T)

    with tab_budget:
        _section_budget(enriched, T, database_url)

    with tab_transactions:
        _section_anomalies(enriched, T)
        st.divider()
        _section_ledger(enriched, T, database_url)
```

### 3o. Default period filter — quick-range selector + all-time Overview

**Problem** (found post-implementation, 2026-07-10): `_build_sidebar_filters` (`app/dashboard.py:415-489`)
defaults its month multiselect to **every month in the data** — a fresh login shows full history with no
scoping, and there's no quick way to land on "what happened recently" without manually narrowing the
multiselect. Desired: sidebar defaults to a recent window (last 30 days) for the day-to-day tabs, while
Overview keeps a full-history feel — but only where "full history" is actually meaningful.

**Decisions** (resolved via discussion):
- Trend-shaped charts (net worth, savings-rate trend, emergency fund) ignore the period filter entirely and
  always show full history — that's their reason to exist.
- Comparison-shaped charts (top-10 category bar, month-over-month) use a bounded recent window (last 12
  months), not true all-time — otherwise they dilute/go stale as history accumulates over years.
- Non-date filters (owner/category/account) still apply everywhere, including the all-time charts — only
  the *date* restriction is bypassed for them.
- Presets anchor to `df["date"].max()`, not `date.today()` — sample/demo data won't be "current", so the
  quick-range must be relative to the latest transaction actually in the data.

**1. Replace the month multiselect with a quick-range selectbox** in `_build_sidebar_filters`:
```python
_PERIOD_PRESETS = ["last_30_days", "current_month", "last_3_months", "last_6_months", "ytd", "all_time", "custom"]

selected_preset = st.sidebar.selectbox(
    T["period_range"],
    options=_PERIOD_PRESETS,
    format_func=lambda key: T[f"period_{key}"],
    index=0,  # "last_30_days"
)
```
- `custom` reveals the existing month multiselect (unchanged) for power users who want to hand-pick specific
  months.
- Each non-custom preset computes a `(start_date, end_date)` window anchored to `df["date"].max()` and
  derives the matching `_month_key` set from it, reusing the existing month-key machinery so downstream code
  doesn't change shape.
- Add `_STRINGS` keys (both "en"/"fr"): `period_range`, `period_last_30_days`, `period_current_month`,
  `period_last_3_months`, `period_last_6_months`, `period_ytd`, `period_all_time`, `period_custom`.

**2. Split the combined mask into date vs. non-date components.** Currently one `mask` combines everything
(`:479-488`). Refactor to:
```python
non_date_mask = (
    df["owner_name"].isin(selected_owners)
    & df["category"].isin(selected_cats)
    & df["account_name"].isin(selected_accounts)
    & (df["amount"].abs() >= amt_range[0])
    & (df["amount"].abs() <= amt_range[1])
    & desc_mask
    & outlier_mask
)
date_mask = df["_month_key"].isin(selected_month_keys)
```
Return `(df[non_date_mask & date_mask], df[non_date_mask], selected_owners)` — the middle value is the new
all-time-but-otherwise-filtered frame. Update the function's return type and its one call site in
`render_dashboard`.

**3. Thread the all-time frame into Overview only.** In `render_dashboard`:
```python
filtered, all_time_filtered, selected_owners = _build_sidebar_filters(tx, T)
...
enriched = _enrich_transactions(filtered)
enriched_all_time = _enrich_transactions(all_time_filtered)
...
with tab_overview:
    _section_net_worth(acct_df, T, lang, selected_owners)
    st.divider()
    _section_overview(enriched, enriched_all_time, acct_df, T, lang, selected_owners)
```
`_section_overview` gains an `all_time_df` parameter:
- Net worth trend, savings-rate trend, emergency-fund indicator → use `all_time_df`.
- Top-10 category bar chart, month-over-month comparison → use `all_time_df` filtered to the trailing 12
  months from `all_time_df["date"].max()`, not the sidebar-selected window.
- The 5 headline KPI metrics (row 1) keep using `df` (the date-scoped frame), so the top of the tab still
  reacts to the quick-range selector.

**4. No special-casing needed for short histories.** If the loaded data spans less than 30 days (fresh demo
data), "Last 30 days" naturally includes everything — it's a date-range filter, not a row-count filter. The
existing "no transactions in filtered set" empty state (`:964-966`) still covers a preset that produces zero
rows (e.g. `Current month` on stale demo data).

**Verification:**
1. Fresh login on sample/demo data → sidebar defaults to "Last 30 days"; Cash flow/Budget/Transactions tabs
   show only that window; Overview's net worth/savings-rate/emergency-fund charts still show full history.
2. Switch to "All time" → the three scoped tabs match Overview's range (sanity-checks the date-mask boundary).
3. Switch to "Custom" → month multiselect reappears and behaves exactly as before this change.
4. Select "Current month" against demo data with no transactions in the current month → empty state, no crash.
5. Apply an owner/account filter → confirm it narrows both the date-scoped and all-time frames identically
   (only the date axis differs between the two).

### 3p. Weekly metrics — add weekly averages alongside monthly (do not replace monthly)

**Note**: this section also touches `_section_overview` and `_section_cash_flow`, which 3o (above) just
changed the shape of (`_section_overview` gains an `all_time_df` parameter; `_build_sidebar_filters` now
returns three values). Implement 3o first, then layer 3p's additions onto the post-3o signatures — the
snippets below assume 3o already landed.

**Problem**: every aggregate added in Phase 3 (savings-rate trend, month-over-month comparison, monthly
net-by-holder, monthly category distribution) buckets by calendar month only. There is no weekly view, so a
user checking mid-month has no sense of *this week's* pace vs the monthly figure. Requirement: add weekly
average metrics **next to** the existing monthly ones — do not fold everything into monthly, and do not
remove any monthly metric.

Implement after 3i/3j (needs `_enrich_transactions` and the Overview/Cash-flow sections to exist) and before
3n (the tab layout must render the new panel).

#### `_enrich_transactions` — add a `week` column

In `app/dashboard.py`, alongside the existing `df["month"] = df["date"].dt.to_period("M").astype(str)` line,
add an ISO-week key (Monday-start, matches `pandas` default week semantics):

```python
df["week"] = df["date"].dt.to_period("W-SUN").astype(str)  # e.g. "2026-07-06/2026-07-12"
```

Use `to_period("W-SUN")` (week ending Sunday) rather than raw ISO week numbers so each bucket carries its
own date range in the label — avoids the year-boundary ambiguity of bare ISO week numbers (e.g. "week 1"
meaning different things across December/January).

#### New `_STRINGS` keys (both "en" and "fr")

```python
"metric_avg_weekly_spend":   "Avg. weekly spend",
"metric_avg_monthly_spend":  "Avg. monthly spend",
"metric_avg_weekly_income":  "Avg. weekly income",
"metric_avg_monthly_income": "Avg. monthly income",
"chart_weekly_trend":        "Income vs. expenses by week",
"axis_week":                 "Week",
```

```python
"metric_avg_weekly_spend":   "Dépense moy. hebdo",
"metric_avg_monthly_spend":  "Dépense moy. mensuelle",
"metric_avg_weekly_income":  "Revenu moy. hebdo",
"metric_avg_monthly_income": "Revenu moy. mensuel",
"chart_weekly_trend":        "Revenus vs. dépenses par semaine",
"axis_week":                 "Semaine",
```

#### Overview tab (`_section_overview`) — weekly + monthly average row

Add a new metrics row directly under the existing Row 1 KPIs (3i), computed from the same `real` frame
(transfers excluded) already built there:

```python
weekly_totals = (
    real.groupby(["week", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0)
)
monthly_totals = (
    real.groupby(["month", "tx_type"])["adjusted_amount"].sum().unstack(fill_value=0)
)

avg_weekly_expense = weekly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0
avg_monthly_expense = monthly_totals.get("expense", pd.Series(dtype=float)).abs().mean() or 0.0
avg_weekly_income = weekly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0
avg_monthly_income = monthly_totals.get("income", pd.Series(dtype=float)).mean() or 0.0

w1, w2, w3, w4 = st.columns(4)
w1.metric(T["metric_avg_weekly_spend"], f"${avg_weekly_expense:,.2f}")
w2.metric(T["metric_avg_monthly_spend"], f"${avg_monthly_expense:,.2f}")
w3.metric(T["metric_avg_weekly_income"], f"${avg_weekly_income:,.2f}")
w4.metric(T["metric_avg_monthly_income"], f"${avg_monthly_income:,.2f}")
```

`.groupby(...).unstack(fill_value=0)` means a week/month with zero expense (or zero income) rows still
contributes a `0` to the average, rather than being silently dropped — averages stay honest about sparse
periods instead of only averaging over active ones.

#### Cash-flow tab (`_section_cash_flow`) — weekly trend chart

Add a weekly counterpart to the existing monthly `chart_mom_bar` (3j.2), placed directly below it so weekly
and monthly sit side by side in the same tab rather than replacing one another:

```python
week_summary = (
    df[df["tx_type"] != "transfer"]
    .groupby(["week", "tx_type"], as_index=False)["adjusted_amount"].sum()
)
week_summary.loc[week_summary["tx_type"] == "expense", "adjusted_amount"] = (
    week_summary.loc[week_summary["tx_type"] == "expense", "adjusted_amount"].abs()
)
fig_week = px.bar(week_summary, x="week", y="adjusted_amount", color="tx_type",
                   barmode="group", title=T["chart_weekly_trend"], template="plotly_white",
                   labels={"adjusted_amount": T["axis_amount"], "week": T["axis_week"]})
st.plotly_chart(fig_week, use_container_width=True)
```

Chart reads left-to-right oldest-to-newest by default since `week` sorts lexicographically the same as
chronologically (the `to_period("W-SUN")` string starts with the ISO date).

#### Tests (extend `tests/test_dashboard_helpers.py`, 6e)

- `test_enrich_transactions_adds_week_column` — one row per week over 3 weeks → 3 distinct `week` values,
  each formatted as a `to_period("W-SUN")` string.
- `test_weekly_average_zero_fills_inactive_weeks` — 3 weeks of data, one with no expense rows → average
  expense divides by 3 (all weeks), not 2 (active weeks only).

#### Ordering note (add to "Ordering constraints / risks")

Phase 3p depends on `_enrich_transactions` (3g) and `_section_overview`/`_section_cash_flow` (3i/3j)
already existing, and on 3o (quick-range filter) having already changed those same functions' signatures
(see the note at the top of this section). It must land before 3n (tab layout) renders the final
`render_dashboard`. It does not touch the Budget tab (3k) — budgets stay monthly-only by design, since a
weekly budget limit isn't a meaningful personal-finance convention.

### 3q. Recurring-transaction tagging — user-taggable `is_recurring` column — Implemented (2026-07-20)

> **Status**: implemented as spec'd below, with one deviation — the migration shipped as
> `database/migrations/006_recurring_transactions.sql`, not `005_...`, since `005_transaction_natural_key.sql`
> (Phase 2.8) had already claimed that number. `update_transaction_recurring` was added to `database/db.py`,
> `t.is_recurring` added to 3e's `tx_query`, and the ledger checkbox column + `edited_rows` handling added to
> `_section_ledger`. `col_recurring` strings added to both `en`/`fr`. Existing tests
> (`test_dashboard_classify.py`, `test_db_hash.py`) still pass unchanged.

**Goal**: let the user manually flag a transaction as recurring (rent, subscriptions, payroll — anything
that repeats month to month), the same way `user_category` (3b/3c) lets them manually override a category.
This is a **user-tagged boolean**, not an ML-detected one — no pattern-matching or auto-detection is in
scope here, only the column and the tagging UI.

**Migration** (new file, e.g. `database/migrations/005_recurring_transactions.sql`, added after the 3c/3p
migrations land, following the same idempotent style):

```sql
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_recurring BOOLEAN NOT NULL DEFAULT FALSE;
```

Defaults to `FALSE` so existing rows are unaffected; the pipeline never writes this column (mirrors the
`user_category` split in 3b — ML/pipeline re-runs must never clobber a manual recurring flag).

**DB method** (`database/db.py`, alongside `update_transaction_category`):

```python
def update_transaction_recurring(self, transaction_hash: str, is_recurring: bool) -> None:
    """Set is_recurring for a transaction (survives pipeline re-runs)."""
    sql = "UPDATE transactions SET is_recurring = %s, updated_at = NOW() WHERE transaction_hash = %s"
    self._execute_many(sql, [(is_recurring, transaction_hash)])
```

**SELECT query** (3e's `tx_query`): add `t.is_recurring` to the selected columns so it flows into `tx_df`
alongside `transaction_hash` and the coalesced `category`.

**Ledger UI** (`_section_ledger`, 3l): add a checkbox column next to the existing category dropdown, using
the same "only act on rows actually edited this cycle" pattern already used for category edits:

```python
T["col_recurring"]: st.column_config.CheckboxColumn(T["col_recurring"]),
```

then in the `edited_rows` loop, handle `T["col_recurring"]` the same way `T["col_cat"]` is handled today,
calling `db.update_transaction_recurring(transaction_hash, bool(new_value))`.

**New `_STRINGS` keys** (both "en" and "fr"):

```python
"col_recurring": "Recurring",
```
```python
"col_recurring": "Récurrent",
```

**Explicitly out of scope for this column** (future phases, not this one): no automatic recurrence
detection, no "recurring transactions" summary view, and no interaction with the weekly/monthly metrics in
3p — `is_recurring` is a taggable attribute only; consuming it in a chart or metric is a separate, later
decision.

---

## Phase 3s — Implemented (2026-07-20): `upsert_transactions` returns insert/update counts

**This phase documents work already shipped**, done outside the original plan — it wasn't spec'd ahead of
time, but is recorded here (following the Phase 2.7/2.8/3r pattern) since it changes a shared method's
signature.

**Problem**: `upsert_transactions` previously returned `None` and logged only a flat row count
(`"Upserted %s transactions"`), which conflates first-time inserts with no-op refreshes of rows already in
the table (e.g. a category/outlier re-stamp on pipeline re-run). Neither the daily pipeline log nor the seed
script's console output could distinguish "120 new transactions landed" from "120 already-seen rows got
touched again."

**What shipped:**
- **`database/db.py::upsert_transactions`** — now returns `tuple[int, int]` (`inserted, updated`). Before
  building the SQL rows, incoming records are deduped by `transaction_hash` within the batch itself (a
  batch containing the same logical transaction twice — e.g. a script re-generating overlapping windows —
  now counts and inserts it once, not twice). Before the `executemany` upsert, a `SELECT transaction_hash
  FROM transactions WHERE transaction_hash = ANY(%s)` against the batch's hash set determines which hashes
  already existed; `updated = len(existing_hashes)`, `inserted = len(rows) - updated`. Log line changed to
  `"Upserted %s transactions (%s new, %s already present)"`.
- **`pipeline/runner.py::run_pipeline`** — unpacks `inserted, updated = database.upsert_transactions(...)`;
  final log line changed to `"Pipeline completed: %s new transactions, %s already present"`. Also added an
  `INFO` log line before the Plaid fetch call (`"Fetching transactions from %s to %s (%s days)"`) for
  visibility into the date window actually requested.
- **`scripts/seed_sample_data.py::main`** — unpacks the same tuple; console output changed to `"Seeded N
  accounts and M transactions (X new, Y already present)."`, making a same-day re-run's no-op behavior
  visible instead of silent.
- **`tests/test_db_upsert_counts.py`** (new) — covers: all-new batch against an empty table, all-updates on
  a same-day rerun, a mixed batch, intra-batch duplicate rows counted/inserted once, and an empty input
  frame short-circuiting before any DB connection is opened.

**Note**: this satisfies part of Phase 6a's planned `tests/test_db_upserts.py` coverage
(`test_upsert_transactions_*` cases) ahead of schedule, under a different filename/scope
(`test_db_upsert_counts.py`, count-behavior only). Phase 6a's remaining cases (accounts, categories, budgets,
`get_categories`, `ensure_schema` migration ordering) are still unimplemented — see Phase 6.

---

## Phase 3r — Implemented (2026-07-19): credit-account inflows are never income; pair-matched internal transfers

**Problem**: `_classify_tx_type` (3a) produced two kinds of fake income. (1) A negative amount on a credit
account matching `_REFUND_KEYWORDS` was classified `"income"` — a card inflow is almost always a payment from
chequing, and even a genuine refund is a reversal of a purchase, not new money. (2) Every negative amount on a
depository/investment account was `"income"`, including money moving from savings → chequing or the chequing
leg of a card payment; the keyword rule only fired on outflows (`amount > 0`), so the two legs of one internal
transfer classified inconsistently. Fixing (2) with keywords alone is wrong: an inbound "e-transfer"/"payment"
on chequing is often money from *another person* — genuine income — so keyword matching can't tell the
difference. The only reliable signal that money is moving inside the user's own accounts is that **both legs
exist in the data**: an outflow on one account and an equal, opposite inflow on a different account within a
few days.

**What shipped:**
- **`app/dashboard.py`** — new `_detect_internal_transfers(df)`, added above `_classify_tx_type`. Buckets rows
  by `amount.abs().round(2)`, then within each bucket greedily pairs each outflow (`amount > 0`) with the
  nearest-in-time unmatched inflow (`amount < 0`) on a *different* `account_name` within `_TRANSFER_MATCH_DAYS`
  (5) days. Matching is one-to-one and consumes candidates as they're paired, so N identical outflows never
  all claim the same inflow. An inflow with no matching outflow anywhere in the data is left alone.
- **`_classify_tx_type` rewrite**: credit + negative + refund-keyword now maps to `"expense"` (was `"income"`)
  — the refund's negative `adjusted_amount` nets against the purchase it reverses inside the same expense
  bucket, rather than inflating income. Credit + negative + no refund keyword is unchanged (`"transfer"`, the
  card-payment case). The `_detect_internal_transfers` mask is applied **last**, overriding every other rule,
  so a paired chequing inflow flips from `income` to `transfer` on both legs while an unpaired inflow (money
  from someone else) still counts as income. Net rule table:

  | account_type | amount | condition | tx_type |
  |---|---|---|---|
  | depository / investment | `< 0` | — | income |
  | depository / investment | `> 0` | payment keyword | transfer |
  | depository / investment | `> 0` | otherwise | expense |
  | credit | `< 0` | refund keyword | expense (nets against spend) |
  | credit | `< 0` | otherwise | transfer |
  | credit | `> 0` | — | expense |
  | unknown/NULL | `< 0` | — | income |
  | any | any | paired internal transfer | transfer (overrides all above) |

- **`render_dashboard`** — moved the single `_enrich_transactions(tx)` call to run on the full unfiltered
  frame *before* `_build_sidebar_filters`, instead of enriching the already-filtered `filtered`/
  `all_time_filtered` frames. Pair matching needs to see both legs of a transfer regardless of which
  owner/account the sidebar filters down to — enriching post-filter would silently turn a transfer back into
  income if the other leg's account got filtered out. `_build_sidebar_filters` needed no change: it filters by
  boolean mask and only drops its own `_month_key`/`_month_label` helper columns, so `adjusted_amount`/
  `month`/`week`/`tx_type` pass through untouched.
- **`tests/test_dashboard_classify.py`** (new) — covers: refund nets to expense (never income) on a credit
  account; unlabelled and labelled credit-card payments stay transfer; unpaired chequing payroll/e-transfer
  inflows stay income; paired cross-account legs (including the seed script's $350 card-payment pair) both
  become transfer; same-account legs are not paired; out-of-window legs are not paired; one-to-one greediness
  holds when multiple same-amount outflows compete for one inflow.

**Known edge case, accepted as out of scope**: expense totals are computed as `abs(sum(...))` over each
group (category/month/etc.), not per row, so refund netting is correct in aggregate — but if a category's
refunds exceed its spend within the filtered period, the group sum goes negative and `abs()` renders it as
positive spend for that category. Rare in practice; not worth restructuring every chart consumer for.

**Amendment to 3a** (`PLAN.md:648-698`): that spec's `_classify_tx_type` body is superseded by this phase —
see the rule table above for the current behavior.

---

## Phase 4 — Docs

> **Status (2026-07-20): implemented.** README rewritten, `docs/setup-google-oauth.md`,
> `docs/setup-plaid.md`, `docs/setup-database.md`, `docs/deployment.md`, and `CONTRIBUTING.md` all created.
> Two deviations from the spec below: (1) the README omits a CI badge, since `.github/workflows/ci.yml`
> doesn't exist yet (Phase 5 is still unimplemented) — a badge pointing at a nonexistent workflow would be
> false; add it when Phase 5 lands. (2) the configuration table lists `SUPABASE_SERVICE_ROLE_KEY` nowhere,
> matching Phase 1b's earlier finding that it has zero usages in the codebase. The 2.5h encryption-at-rest
> decision is now documented in the README's Security section as originally planned.

### 4a. Rewrite `README.md`

Structure (link to `docs/` for depth; keep each section skimmable):

```markdown
# automated-financial-intelligence

> Modular personal-finance platform: ingest bank transactions → classify with ML →
> persist in PostgreSQL → explore in a secure Streamlit dashboard. Built for self-hosting.

[CI badge] [License badge] [Python 3.12+ badge]

## Screenshots
<!-- Capture after running on sample data -->

## Architecture
[Mermaid or ASCII: Plaid → pipeline/runner.py → DB → dashboard; seed script → DB (demo path)]

| Layer | Path | Responsibility |
|-------|------|----------------|
| Ingestion | ingestion/ | Fetch + normalize (Plaid; `BaseIngestor` seam for future sources) |
| Database | database/ | Idempotent upserts via sha256 hash; auto-run migrations |
| Analytics | analytics/ | ML classifier + outlier detector (placeholder in Phase 1) |
| Core | core/ | Config, Google OAuth/PKCE, session |
| Pipeline | pipeline/runner.py | Orchestrate ingest → classify → persist |
| App | app/ | Streamlit dashboard (4 tabs, bilingual EN/FR) |

Key design decisions (interview talking points):
- Hash-based idempotent upserts: sha256(account_name|date|description|amount) → safe to re-run daily
- Config-load vs. pipeline-run validation split: load_settings() never requires Plaid creds, so dashboard-only and seed-demo deployments run credential-free; the pipeline enforces them at build time
- Runtime migrations: ensure_schema() runs all database/migrations/*.sql sorted — no migration tooling
- Two-column category design: pipeline writes `category`; user edits write `user_category`; dashboard reads COALESCE
- OAuth+PKCE: full Google sign-in without a heavyweight framework; 4-hour session expiry
- Config precedence: env → .streamlit/secrets.toml → default via load_settings()
- Placeholder seam: swap build_placeholder_models() → build_models(settings) with no orchestration changes

## Quickstart (local with docker — no Plaid account needed)
`docker compose up -d` → `python scripts/seed_sample_data.py` → `streamlit run app/streamlit_app.py`
Python 3.12+ required. Run all commands from repo root. Plaid credentials are only needed to ingest real data via `python main.py`.

## Configuration reference
[Table from core/config.py — ONLY real vars, grouped]

## Ingesting your own data
Plaid setup (sandbox + production) → docs/setup-plaid.md; database options → docs/setup-database.md

## Project status & roadmap
✅ Data path: ingest → persist → dashboard
✅ Dashboard: 4 tabs, bilingual EN/FR, budgets, inline category editing
🔄 ML: classifier and outlier detector exist; pipeline uses placeholders (Phase 7)

## Security
- Auth: Google OAuth (PKCE S256) + verified-email allowlist, fails closed; 4-hour sessions
- Transport: TLS enforced in code on all remote DB connections (sslmode=require auto-appended)
- At rest: managed-Postgres disk encryption (Supabase/Neon); app-level column crypto deliberately
  not used — see design decisions
- Secrets: env vars / GitHub Secrets only, nothing committed; hash-locked dependencies
  (--require-hashes); SHA-pinned CI actions
- Public/mobile deployments: HTTPS redirect URI required; DB errors never rendered to the browser

## Contributing / License
```

### 4b. Create `docs/setup-google-oauth.md`

Steps:
1. GCP console → create project.
2. APIs & Services → OAuth consent screen → External → add your email as a test user.
3. Credentials → Create OAuth client ID → Web application.
4. Authorized redirect URIs: exactly `http://localhost:8501/` for local dev (must match
   `GOOGLE_OAUTH_REDIRECT_URI`); for a public deployment add the **HTTPS** dashboard URL as a second
   redirect URI and point the env var at it (required for mobile sign-in).
5. Copy Client ID + Secret into `.env`.
6. Set `GOOGLE_ALLOWED_EMAILS`.

Troubleshooting table:
- `redirect_uri_mismatch` → URI in GCP must exactly match the env var.
- "App not verified" → add email as test user in consent screen.
- "Session expired" → Streamlit restarted; sign in again (4-hour expiry by design).

### 4c. Create `docs/setup-plaid.md`

Sandbox: `python scripts/create_sandbox_access_token.py --append`. Set `PLAID_ACCESS_TOKEN_OWNERS` positionally aligned with `PLAID_ACCESS_TOKENS` (see `pipeline/runner.py:52`).
Production: change `PLAID_BASE_URL`; no Link UI in repo — tokens minted externally.

### 4d. Create `docs/setup-database.md`

Three options: docker (default, matches `.env.example`), Supabase (pooler URL port 6543), Neon (add `?sslmode=require`). Note that `ensure_schema()` runs all migrations idempotently on every startup.

### 4e. Create `docs/deployment.md`

GitHub Actions Secrets table:
| Secret | Notes |
|--------|-------|
| `DATABASE_URL` | Required |
| `PLAID_CLIENT_ID` | |
| `PLAID_SECRET` | |
| `PLAID_ACCESS_TOKENS` | Comma-separated |
| `PLAID_ACCESS_TOKEN_OWNERS` | Comma-separated, positionally aligned |
| `PLAID_BASE_URL` | |

Note: OAuth secrets (`GOOGLE_OAUTH_*`) are **not** needed by the pipeline workflow — only by the dashboard.

Activation: workflow only runs from `main` + Secrets populated. Streamlit Community Cloud: update `GOOGLE_OAUTH_REDIRECT_URI` to the deployed URL.

### 4f. Create `CONTRIBUTING.md`

Dev setup → test command → layer conventions (no personal data; config only via `Settings`/`.env.example`; strict layer boundaries; run from repo root) → PR checklist (CI green, no personal data). Known cosmetic issue: `pd.read_sql` on raw psycopg connection emits a `UserWarning` — roadmap, not fixed now.

---

## Phase 5 — CI / workflows

> **Status (2026-07-20): implemented.** `.github/workflows/ci.yml` created per 5a, with `actions/checkout`
> and `actions/setup-python` pinned to real full-commit SHAs (v7.0.1 and v7.0.0 respectively, resolved via
> the GitHub API at implementation time, not the placeholder `<full-commit-SHA>` text in the spec below).
> `.github/workflows/daily-finance-pipeline.yml` updated per 5b: header comment added, `ALLOWED_EMAILS` /
> `DASHBOARD_PASSWORD` / `CSV_PATHS` / `INGESTION_SOURCE` / `LABELED_DATASET_PATH` removed from `env`,
> `PLAID_ACCESS_TOKEN_OWNERS` added, both actions pinned to the same SHAs as 5a, install switched to
> `pip install --require-hashes -r requirements.lock`, `timeout-minutes: 15` added to the job, and a
> `concurrency` guard (`group: daily-pipeline`) added at the workflow level. `MODEL_PATH` was left in `env`
> since the spec only calls out `CSV_PATHS`/`INGESTION_SOURCE`/`LABELED_DATASET_PATH` for removal. No secret
> values were read or written as part of this work — Secret population on GitHub is a manual Phase 0 step
> for the repo owner.

### 5a. Create `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, dev]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@<full-commit-SHA>  # vX.Y.Z — resolve latest release SHA at implementation time
      - uses: actions/setup-python@<full-commit-SHA>  # vX.Y.Z — resolve latest release SHA at implementation time
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install --require-hashes -r requirements.lock
      - run: python -m unittest discover -s tests -v
```

No DB, network, or secrets needed — all tests are pure (mock everything).

Security notes (2026-07-07 review): actions are pinned to **full commit SHAs** (with the tag in a trailing
comment), not mutable tags — a compromised `v4` tag would otherwise execute in workflows, including the
secrets-bearing daily job. Installs use the hash-locked `requirements.lock` (Phase 1f).

### 5b. Modify `.github/workflows/daily-finance-pipeline.yml`

1. Add header comment: `# Inert until repository Secrets are set and this workflow is on the default branch (main). See docs/deployment.md.`
2. Delete from `env:` block:
   ```yaml
   ALLOWED_EMAILS: ${{ secrets.ALLOWED_EMAILS }}
   DASHBOARD_PASSWORD: ${{ secrets.DASHBOARD_PASSWORD }}
   ```
3. Add:
   ```yaml
   PLAID_ACCESS_TOKEN_OWNERS: ${{ secrets.PLAID_ACCESS_TOKEN_OWNERS }}
   ```
4. Remove `CSV_PATHS`, `INGESTION_SOURCE`, and `LABELED_DATASET_PATH` from env (`CSV_PATHS`/`INGESTION_SOURCE` no longer exist as config keys after Phase 2a; ML not wired).
5. Security hardening (2026-07-07 review):
   - Pin `actions/checkout` and `actions/setup-python` to full commit SHAs (same as 5a).
   - Install via `pip install --require-hashes -r requirements.lock` (Phase 1f).
   - Add to the job: `timeout-minutes: 15` — a hung Plaid call would otherwise hold Plaid + DB secrets in a
     live runner for GitHub's 6-hour default.
   - Add a concurrency guard so a manual `workflow_dispatch` can't race the cron run's upserts:
     ```yaml
     concurrency:
       group: daily-pipeline
       cancel-in-progress: false
     ```

---

## Phase 6 — Tests

> **Status (2026-07-20): implemented — but uncommitted.** 6a–6g are all written and passing; only **6h**
> (the optional pytest migration) remains, and it is deliberately deferred. The suite now runs **99 tests,
> all green**, up from the 33 recorded earlier in this plan. Six new files landed —
> `tests/test_db_upserts.py` (6a, 245 lines, supersedes the older `test_db_upsert_counts.py`),
> `test_pipeline_runner.py` (6b), `test_config.py` (6c), `test_outlier_detector.py` (6d),
> `test_dashboard_helpers.py` (6e), `test_seed_sample_data.py` (6f) — plus the 6g auth-security cases
> appended to the existing `tests/test_app_auth.py`. All use `unittest.mock` throughout; none touches a
> live DB or the network, as required below.
>
> **Runner caveat:** the system `python` on PATH lacks `psycopg`, so `python -m unittest discover -s tests`
> errors on 8 tests from a bare shell. Use the project virtualenv's interpreter
> (`venv_automated_financial_intelligence/Scripts/python.exe`) to get the real 99-test result.

All tests must be pure — no live DB, no network. Mock seam for DB: `@patch("database.db.psycopg.connect")`. All `pipeline.runner` deps patchable at `pipeline.runner.*`.

### 6a. `tests/test_db_upserts.py`

- `test_upsert_plaid_accounts_full_row` — dict with all fields (owner/official_name/type/subtype/balances/currency) → SQL params include every value in order.
- `test_upsert_plaid_accounts_missing_optionals_are_none` — dict with only `account_key`/`account_name`/`source` → optional params are `None`, no exception.
- `test_upsert_plaid_accounts_empty_list_skips` — empty list → `_execute_many` not called.
- `test_upsert_transactions_hash_stable` — same dict input → same hash every call.
- `test_upsert_transactions_empty_id_to_none` — `transaction_id = ""` → `external_id = None`.
- `test_upsert_transactions_account_key_fallback` — no `account_key` column → `"unknown:unknown"`.
- `test_upsert_categories_dedup_and_sort` — `["b", "a", "a"]` → `[("a",), ("b",)]`.
- `test_upsert_categories_skips_empty` — empty input → `_execute_many` not called.
- `test_get_categories_returns_list` — mock cursor returns `[("Groceries",), ("Transport",)]` → list of strings.
- `test_get_budgets_returns_list` — mock cursor returns rows → `[{"category": ..., "monthly_limit": ...}]`.
- `test_upsert_budget_calls_execute` — correct SQL and param tuple.
- `test_update_transaction_category_writes_user_category` — assert the UPDATE SQL targets `user_category`, not `category`; assert categories INSERT also runs in same call.
- `test_ensure_schema_runs_all_migrations_sorted` — mock `pathlib.Path.glob` to return two `.sql` Path objects; assert `cursor.execute` called twice in sorted name order.

### 6b. `tests/test_pipeline_runner.py`

Patches: `pipeline.runner.load_settings`, `pipeline.runner.PlaidIngestor`, `pipeline.runner.DatabaseClient`.

- `test_build_ingestor_returns_plaid` — full creds → `PlaidIngestor` constructed with client_id/secret/tokens/base_url.
- `test_build_ingestor_missing_client_id` — no client_id → `ConfigError`.
- `test_build_ingestor_missing_secret` — no secret → `ConfigError`.
- `test_build_ingestor_empty_tokens` — `plaid_access_tokens=[]` → `ConfigError`.
- `test_build_ingestor_owner_token_mismatch` — 2 tokens, 1 owner → `ConfigError` (misalignment would mislabel account owners).
- `test_run_pipeline_happy_path` — non-empty frame → `upsert_categories` and `upsert_transactions` called; frame has `category` (str) and `is_outlier` (bool) columns.
- `test_run_pipeline_empty_frame` — empty frame → no DB calls; returns empty DataFrame.
- `test_run_pipeline_calls_upsert_plaid_accounts` — `fetch_accounts` called with the owner-by-token map; result passed to `upsert_plaid_accounts`.

### 6c. `tests/test_config.py`

Use `@patch("core.config.load_dotenv")` + `@patch.dict(os.environ, {...}, clear=True)`.

- `test_database_url_required` — no `DATABASE_URL` → `ConfigError`.
- `test_plaid_optional_at_load` — only `DATABASE_URL` set → `load_settings()` succeeds; `plaid_client_id`/`plaid_secret` are `None`, token lists empty. (Guards the seed-demo / dashboard-only path.)
- `test_plaid_values_read` — all Plaid vars set → populated on `Settings`.
- `test_plaid_base_url_default` — unset → `https://sandbox.plaid.com`.
- `test_env_over_secrets_precedence` — env value beats secrets.toml value.
- `test_google_allowed_emails_split` — `GOOGLE_ALLOWED_EMAILS=a@b.com,c@d.com` → list of two.
- `test_plaid_access_token_owners_split` — comma-separated → list.
- `test_plaid_access_tokens_split` — `PLAID_ACCESS_TOKENS=t1,t2` → `["t1", "t2"]`.
- `test_enforce_tls_appends_sslmode_for_remote_host` — `postgresql://u:p@db.example.com/x` → ends with `?sslmode=require`.
- `test_enforce_tls_skips_localhost` — `postgresql://u:p@localhost:5433/x` and `...@127.0.0.1/x` → unchanged.
- `test_enforce_tls_preserves_existing_sslmode` — `...?sslmode=verify-full` → unchanged (never downgraded).
- `test_enforce_tls_appends_with_ampersand` — remote DSN with an existing query param → `&sslmode=require`.
- `test_load_settings_applies_enforce_tls` — remote `DATABASE_URL` env → `settings.database_url` contains `sslmode=require`.

### 6d. `tests/test_outlier_detector.py`

`OutlierDetector` uses `random_state=42` (confirmed at `outlier_detector.py:39`) — tests can rely on deterministic output.

- `test_score_empty_frame` — empty DataFrame → returns empty with `outlier_score` and `is_outlier` columns.
- `test_score_small_group_uses_zscore` — fewer than 8 rows; one amount 10× the mean → `is_outlier=True` for that row.
- `test_score_large_group_uses_isolation_forest` — 20 uniform rows + 1 extreme outlier → the extreme row has `is_outlier=True`.
- `test_score_preserves_all_rows` — output row count equals input row count.
- `test_outlier_score_dtype` — `outlier_score` column is float64.

### 6e. `tests/test_dashboard_helpers.py`

Pure pandas — no Streamlit runtime. Import `_classify_tx_type`, `_label_subtype` from `app.dashboard`.

`_classify_tx_type` test matrix (build a 1-row DataFrame for each case):
- `test_depository_negative_is_income` — type=depository, amount=-100 → "income".
- `test_depository_positive_payment_is_transfer` — type=depository, amount=100, desc="Credit Card Payment" → "transfer".
- `test_depository_positive_no_keyword_is_expense` — type=depository, amount=100, desc="Groceries" → "expense".
- `test_credit_positive_is_expense` — type=credit, amount=50 → "expense".
- `test_credit_negative_refund_is_income` — type=credit, amount=-25, desc="Cashback reward" → "income".
- `test_credit_negative_no_refund_is_transfer` — type=credit, amount=-350, desc="Payment - Thank You" → "transfer".
- `test_unknown_account_type_negative_is_income` — type=None, amount=-500 → "income".
- `test_unknown_account_type_positive_is_expense` — type=None, amount=30 → "expense".
- `test_investment_negative_is_income` — type=investment, amount=-200 → "income".

`_label_subtype`:
- `test_known_subtype_en` — `"tfsa"` → `"TFSA"`.
- `test_known_subtype_fr` — `"checking"` + lang=fr → `"Compte-chèques"`.
- `test_unknown_subtype_titlecased` — `"brokerage"` → `"Brokerage"`.
- `test_none_subtype` — `None` → `"Other"`.

### 6f. `tests/test_seed_sample_data.py`

Pure — patch `DatabaseClient` where the seed script imports it (e.g. `@patch("scripts.seed_sample_data.DatabaseClient")`). Structure the script with a `generate(days) -> (accounts, frame)` function separate from `main()` so generation is testable without any DB mock.

- `test_generate_produces_rows` — `generate(120)` → frame has >100 rows; all required columns present (`date, description, amount, balance, account_name, source, transaction_id, category, outlier_score, is_outlier`).
- `test_generate_both_owners_present` — accounts list contains all 5 accounts; `owner_name` values include both `Alex` and `Sam`.
- `test_generate_anomalies_flagged` — exactly 3 rows with `is_outlier=True`, each with `outlier_score == 0.9`.
- `test_generate_categories_canonical` — set of `category` values ⊆ the Phase 3c seed list (title case).
- `test_generate_transfer_pair` — the monthly credit-card payment posts as a −350/+350 pair, both `category="Transfer"`.
- `test_generate_source_is_sample` — every row has `source == "sample"`.
- `test_generate_deterministic` — two calls with the same `days` → identical frames (`assert_frame_equal`).
- `test_main_calls_db_in_order` — mocked client: `ensure_schema`, `upsert_plaid_accounts`, `upsert_categories`, `upsert_transactions` all called.

### 6g. Auth security tests (extend `tests/test_app_auth.py`)

Cover the Phase 2.5b/2.5d hardening. Mock `requests` at `core.google_oauth.requests`; drive
`app.auth` with a fake `st.session_state` / `st.query_params` as the existing tests do.

- `test_unverified_email_rejected` — userinfo payload with `email_verified: false` and an allowlisted email → `is_authorized_identity` returns `False`.
- `test_verified_email_on_allowlist_accepted` — `email_verified: true` + allowlisted email → `True`.
- `test_missing_email_verified_claim_rejected` — payload without the claim → `False` (fails closed).
- `test_pending_state_expires_after_ttl` — insert a pending entry with `created_at` 601s in the past; callback with its state → rejected via the "session expired" path.
- `test_pending_state_capped` — insert 32 entries; `start_google_sign_in` → oldest evicted, size ≤ 32.
- `test_auth_url_has_no_offline_access` — `build_authorization_url(...)` output does not contain `access_type=offline` (2.5c).

### 6h. (optional / not blocking / deferred) Adopt `pytest` as the test runner

> Renumbered from `6g` on 2026-07-20 — this section and the auth-security tests above were both numbered
> `6g`. The auth tests kept the letter (they shipped as part of the 6a–6g batch); this one moved to `6h`
> and was reordered to sit last, which also reflects that it is the only part of Phase 6 still open.

Found 2026-07-19: `pytest` already collects and runs the existing `unittest.TestCase`-based suite as-is —
no rewrite required, it's a drop-in runner. The only friction seen was environmental (bare `pytest`, run
outside the project venv and without a repo-root `conftest.py`/`pythonpath` config, can't resolve
`from app import auth` etc.), not a framework incompatibility.

If ever adopted:
- Add `pytest` to dev dependencies (not `requirements.txt` proper — it's not a runtime dep).
- Add to `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  pythonpath = ["."]
  testpaths = ["tests"]
  ```
  so bare `pytest` resolves imports without needing `python -m pytest` or a `conftest.py`.
- Update the `CLAUDE.md` test commands (`python -m unittest discover -s tests -v` → `pytest`) and Phase 5
  CI workflow's test step accordingly.
- Optional follow-up, not required for pytest to work: convert `TestCase`/`assertEqual`-style bodies to
  plain `assert` functions and use `@pytest.mark.parametrize` for the table-driven cases (e.g. the
  `_classify_tx_type` matrix in 6e, the `google_oauth` allow/block cases) — nicer diffs and less
  boilerplate, but with ~13-30 tests total the payoff is modest; only worth it if pytest fixtures/parametrize
  end up used elsewhere too.

---

## Phase 7 — DEFERRED: ML activation

Explicitly out of initial publish scope. Do after Phases 1-6 land and the repo is public.

- [ ] `core/config.py`: add `ML_MODE` (`placeholder` | `real`, default `placeholder`) to `Settings` + `.env.example`.
- [ ] Create `analytics/models.py::build_models(settings) -> ModelBundle`: returns placeholder or `TransactionClassifier(settings.model_path)` + `OutlierDetector()` — both share the same duck-type interface (`categorize(Series)` / `score(DataFrame)`).
- [ ] `pipeline/runner.py:44`: `build_placeholder_models()` → `build_models(settings)`.
- [ ] Create `scripts/train_classifier.py`: loads settings, calls `TransactionClassifier.train(labeled_dataset_path)`, prints holdout accuracy. Rule-based fallback means `ML_MODE=real` degrades gracefully untrained.
- [ ] Implement `scripts/seed_sample_data.py --labeled` flag: writes `data/sample/labeled_transactions.csv` (`description,category`) from the same merchant pool — the seed script already pairs every description with its canonical category, so this is a two-column dump → train → pipeline → categorized dashboard in 3 commands.
- [ ] Tests: extend `test_classifier.py` (train on synthetic, assert accuracy > 0.5); add `tests/test_models_builder.py` (mode switch).
- [ ] Update README roadmap.

---

## Phase 8 — Code quality: modularity, comments, conventions (verification gate)

A pass to confirm new code is modular, commented where non-obvious, and conventionally styled — enforced
by a review checklist (8b) **and** an automated ruff gate in CI (8a).

### 8a. Tooling — ruff (lint + format) in CI

> **Amended 2026-07-20 — black is dropped in favour of `ruff format`.** This section originally specified
> ruff *and* black, written before ruff's formatter was a viable black replacement. It now is:
> `ruff format` is black-compatible by design, so output is effectively identical, but it is one tool, one
> config block, one pinned version, and it installs and runs an order of magnitude faster. Two further
> decisions were locked at the same time: **`line-length = 110`** (as originally proposed — measured below),
> and the lint job is **blocking from its first run**, not soft-launched.
>
> Status: **implemented 2026-07-21.** `ruff==0.15.22` resolved and pinned; `[tool.ruff]`/`[tool.ruff.lint]`
> added to `pyproject.toml`; `ruff format .` + `ruff check --fix .` applied repo-wide; the 15 over-length
> lines hand-wrapped; the genuine `B`/`UP` findings reviewed individually (see below) — none were blanket
> `--fix`ed; `lint` job added to `ci.yml` as a sibling of `test`; `CONTRIBUTING.md` documents the tooling
> and PR checklist gained the `ruff check . && ruff format --check .` bullet.
>
> **Findings that needed judgment, not autofix:** `pipeline/runner.py`'s `zip(plaid_access_tokens,
> plaid_access_token_owners)` got `strict=False` explicit (not `True` — owners is intentionally optional,
> and `_build_ingestor` only enforces equal length when owners is non-empty; `strict=True` would raise on
> the legitimate "no owners configured" case). Its `except psycopg.OperationalError` gained
> `raise SystemExit(1) from None`, matching the already-decided Phase 2.5 security posture (don't leak a
> DSN-bearing traceback). `scripts/dedupe_accounts.py`'s `zip(columns, row)` got `strict=True` (safe —
> `cur.description` and each fetched row are guaranteed equal length by the DB-API). Three unused
> `for owner, account_name in ...` loop vars in `scripts/seed_sample_data.py` and one in
> `analytics/outlier_detector.py` were renamed `_owner`/`_category`. `tests/test_placeholders.py`'s
> `(scored["is_outlier"] == False).all()` was rewritten to `(~scored["is_outlier"]).all()` — ruff's own
> suggested text (`not scored["is_outlier"]`) would have raised `ValueError: truth value of a Series is
> ambiguous`; the E712 autofix is unsafe for pandas Series for exactly this reason.

**State *before* this work, kept for context (measured 2026-07-20):**

- `.github/workflows/ci.yml` has exactly one job, `test` (matrix `["3.12", "3.13"]`, actions SHA-pinned per
  Phase 5, installs via `pip install --require-hashes -r requirements.lock`). No linting of any kind runs.
- `pyproject.toml` is 19 lines with no `[tool.*]` section at all.
- Neither `ruff` nor `black` is installed locally, and neither is in `requirements.txt` / `requirements.lock`.
  They stay **dev-only** — never added to the hash-locked runtime deps.
- 31 tracked `.py` files. Lines exceeding 110 chars, by file: `scripts/seed_sample_data.py` (5),
  `app/dashboard.py` (5), `database/db.py` (2), `scripts/create_sandbox_access_token.py` (2),
  `app/auth.py` (1) — **15 lines across 5 files**, longest 154. Small enough to fix in one pass, which is
  what makes the blocking-from-day-one decision affordable.

#### `pyproject.toml` — append (do not rewrite; 1c's structure stays)

```toml
[tool.ruff]
line-length = 110
target-version = "py312"
extend-exclude = ["venv_automated_financial_intelligence"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]   # pycodestyle, pyflakes, isort, pyupgrade, bugbear
```

Two deliberate deviations from the original snippet above: `target-version` is **`py312`**, not `py311` —
`requires-python = ">=3.12"` (1c) and CI tests 3.12/3.13, so `py311` would suppress pyupgrade rewrites the
project can actually use. And there is no `[tool.black]` section. `extend-exclude` covers the local
virtualenv (`CLAUDE.md`: never edit or search inside it); ruff also honours `.gitignore` by default, so
this is belt-and-braces.

#### Discovery pass — run before touching any code

Ruff has never run on this tree, so the violation set is unmeasured. Run first, read the output, *then* edit:

```bash
pip install ruff              # note the resolved version — it becomes the CI pin
ruff check .                  # lint findings
ruff format --diff .          # what the formatter would rewrite, without writing
```

Expect three classes of finding, which must be handled **differently**:

| Class | Rules | How to handle |
|---|---|---|
| Pure formatting | — | `ruff format .` — mechanical, no review needed |
| Import order / unused imports | `I`, `F401` | `ruff check --fix .` — safe, but eyeball the diff |
| Real findings | `B` (bugbear), `UP` | **Review individually. Do not blanket-`--fix`.** B-rules surface genuine bugs (mutable default args, loop-variable binding) that deserve a real fix, not a rewrite |

If a `B` or `UP` finding implies a behavioural change, **stop and raise it** — this is a formatting pass, not
a refactor. Genuine false positives get a narrowly-scoped `# noqa: <rule>` with a comment explaining why,
never a blanket rule removal from `select`.

#### Fix the 15 over-length lines

`ruff format` wraps most long lines, but not long string literals, comments, or URLs. Hand-wrap whatever
`ruff check .` still reports as `E501` afterwards, in the five files listed above. Preserve meaning exactly
— several of these are docstrings and comments recording non-obvious invariants (the Plaid sign convention,
why `user_category` exists). **Rewrap, don't rewrite.**

#### `.github/workflows/ci.yml` — add a `lint` job

Sibling of the existing `test` job under `jobs:`, so the two run in parallel:

```yaml
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install ruff==0.15.22
      - run: ruff check .
      - run: ruff format --check .
```

- **Reuse the exact SHA pins already at `ci.yml:17-18`** — do not re-resolve them. Phase 5 requires
  SHA-pinned actions and those two are already verified for this repo.
- **Pin the ruff version explicitly.** An unpinned `pip install ruff` lets a new ruff release turn a green
  `main` red with no code change. Use the version resolved in the discovery pass, so local and CI agree.
- Single Python version — lint results do not vary across 3.12/3.13, so a matrix wastes CI minutes.
- **No `continue-on-error`** — blocking from the first run.
- The job deliberately does **not** install `requirements.lock`: ruff needs no project deps, so skipping the
  install makes it finish in seconds.

#### `CONTRIBUTING.md` — document the tooling

New `## Linting and formatting` section between `## Running things` and `## Conventions`, stating that ruff
is a dev tool deliberately absent from `requirements.txt`/`requirements.lock`, and listing
`pip install ruff==0.15.22` / `ruff check .` / `ruff check --fix .` / `ruff format .`, plus the note
that CI runs `ruff check .` and `ruff format --check .` and fails on any violation, with config in
`pyproject.toml`. Also add one bullet to the existing `## Before opening a PR` list:

- `ruff check .` and `ruff format --check .` both pass.

#### Commit structure

Three commits, in this order, so mechanical noise never hides a real change:

1. `style: apply ruff format and autofixes` — `ruff format .` + `ruff check --fix .` output plus the
   hand-wrapped `E501` lines. **No behavioural change.**
2. `fix: <specific>` — **only** if the discovery pass surfaced genuine `B`/`UP` findings worth fixing. Skip
   this commit entirely if there are none.
3. `ci: add ruff lint and format gate` — `pyproject.toml` config, the `lint` job, `CONTRIBUTING.md`, and
   marking this section done.

### 8b. Review checklist (manual gate before `dev → main`)

- **Layer boundaries:** no DB access outside `database/`; no Streamlit outside `app/`; config read only via
  `core/config.py`. A change in one layer does not reach into another (`CLAUDE.md` convention).
- **Single responsibility:** new dashboard sections are one `_section_*` function each; DB access is one
  method each; no multi-purpose helpers.
- **Docstrings:** every new public function/method has a one-line docstring; non-obvious invariants get a
  comment — especially the **Plaid sign convention** (positive = outflow) and **why `user_*` columns exist**
  (pipeline never writes them). Match the existing comment density; don't over-comment obvious code.
- **Naming:** matches the existing concise style (`_section_budget`, `upsert_budget`, `T[...]` i18n keys).
- **No personal data / no inline config:** no hardcoded emails, tokens, paths; new tunables go through
  `Settings` + `.env.example`.
- **i18n parity:** every new UI string exists in both `en` and `fr` `_STRINGS`.

### 8c. Verification

```bash
# 1. Both halves of the tooling gate pass locally
ruff check .
ruff format --check .

# 2. Formatting changed nothing behavioural — the suite must stay green
python -m unittest discover -s tests -v      # 99 tests, all passing (use the venv interpreter)

# 3. Nothing personal leaked in (reaffirms the Phase-level rule)
git grep -E "jacos|jacosse|gmail\.com|C:\\\\Users"    # expect no matches

# 4. The app still runs — formatting touches app/dashboard.py and app/auth.py
python scripts/seed_sample_data.py            # needs DATABASE_URL only
streamlit run app/streamlit_app.py            # sign in, click through all four tabs
```

Then push the branch and confirm on GitHub that **both** `test` (2 jobs) and `lint` (1 job) appear and go
green. To prove the gate actually bites, temporarily push a deliberately mis-formatted line and confirm CI
goes red before removing it.

**Do not run `python main.py`** as verification — it hits live Plaid and writes production data. The seed
script is the safe equivalent.

---

## Phase 9 — Mobile-friendly dashboard (all fronts)

> **Goal**: the dashboard is genuinely usable on a phone — every tab, chart, table, and filter — not merely
> reachable from one. Status: **code implemented 2026-07-27 on `dev`, device verification outstanding**.
> **Non-blocking** for the `dev → main` publish merge: the app renders on mobile today, it is just cramped
> and sprawling. Schedule after Phase 3.
>
> **Implementation status (2026-07-27).** 9a–9f are implemented in the working tree on `dev`; 152 tests pass
> and `ruff check`/`ruff format` are clean.
>
> **Browser-verified so far** (local `streamlit run`, Chrome): the stylesheet reaches the DOM and all 7
> rules in the `max-width: 640px` block parse as valid, `:has()` included; `initial_sidebar_state="collapsed"`
> works; and the CSS is present **on the sign-in page while unauthenticated** — the concrete proof of
> amendment 2, since the originally-specified call site could not have styled that screen. This pass is also
> what uncovered the literal-style-tag bug documented below, which had been silently voiding the entire
> stylesheet.
>
> **Still unverified — the visual half of 9g.** Chrome refused to size its window below ~1660px and the
> dashboard itself sits behind Google sign-in, so *none* of the following has been seen: KPI rows wrapping
> 2-up, chart legends below plots, table behaviour, FR tab-bar fit, or the absence of horizontal page
> scroll. The rules are known to exist and parse; whether they *look right* at 390px is untested. Use
> DevTools device emulation (not window resizing) plus a real signed-in session. Treat that as the gate
> before this phase is called done.
>
> Git operations are the user's: nothing here is committed, merged, or pushed.

### Decisions locked (2026-07-27 grilling session)

| # | Decision | Rationale |
|---|---|---|
| 1 | Amount-range two-handle slider → **two `number_input`s**, globally | Sliders are imprecise for numeric entry on any device; touch merely exposes it. Applied to desktop too, because decision 2 of the 2026-07-19 set forbids divergent per-viewport widgets. |
| 2 | `initial_sidebar_state="collapsed"` | Mobile opens to the dashboard, not the filter drawer. Deliberate tradeoff: desktop gains one click. |
| 3 | Inject CSS in **`main()`**, absorbing the pre-existing inline block-container rule | See amendment 2 — the originally-specified call site would have left the sign-in page unstyled. |
| 4 | `column_config` on **all 4** tabular widgets | See amendment 4 — there are 4 now, not the 2 originally scoped. |
| 5 | Ship 2 unit-test classes: stylesheet integrity + `_style_chart` | Layout regressions here are silent (no exception, no warning) — the same failure class as the gotcha above. Follows the Phase 2.6a precedent of testing an attribute that had already caused two bugs. |
| 6 | **Skip** `.streamlit/config.toml` | It is global with no viewport targeting, so `[theme] baseFontSize` would change desktop equally; `mobile.css`'s `@media` block achieves mobile-only density with zero desktop impact. Kept as a separate future decision. |
| 7 | Verify on `dev` via DevTools emulation; real-device pass **after** the user merges | SCC tracks `main` and auto-redeploys, so real devices can only be reached post-merge. Acceptable because every rule is additive — rollback is deleting `mobile.css`. |

### Amendments found by verifying this phase against the code (2026-07-27)

The phase text below was written 2026-07-19 and had drifted. Corrections:

1. **Line numbers drifted ~120–160 lines** — `dashboard.py` was 1325 lines before this phase; the text's
   highest reference was 1158. Structure was intact (metric rows still 3/5/4/6 columns, still exactly 12
   `plotly_chart` calls), so only the anchors were stale. **Anchor on symbol names, not line numbers.**
2. **9a's call site was wrong and is superseded by decision 3.** It specified `render_dashboard`. But
   `main()` returns early when the user is not signed in, so the **sign-in page — the first screen every
   mobile user sees — would have received no styling at all.** Injecting in `main()` covers sign-in, sidebar
   and dashboard alike.
3. **The module-scope gotcha was already fixed.** `st.set_page_config` and an `st.html` CSS block already sat
   inside `main()`. The gotcha section stays as documentation; its fix had landed 2026-07-26. That inline
   rule is now absorbed into `mobile.css` so styling has one home.
4. **9d undercounted the tables: 4, not 2.** Added since the phase was written: a credit-limit editor in
   `_section_net_worth` and the budget editor. Both are narrow, so both got width hints only.
5. **9c's uniform `hovermode="x unified"` was wrong for 3 of the 12 figures** — two are `px.pie` (no x-axis)
   and one is `orientation="h"` (needs `y unified`). `_style_chart` therefore takes a `hovermode` parameter
   (`None` = leave Plotly's default). The horizontal bar is also the top-categories chart, so it takes both
   `height=380` and `hovermode="y unified"`.

### Gotcha: a literal style tag inside the CSS file silently voids the ENTIRE stylesheet

> Found 2026-07-27 during browser verification. Read this before editing `app/static/mobile.css`. Like the
> module-scope gotcha above, the failure mode is **completely silent** — no browser console error, no server
> log warning, no exception, and `st.html()` reports success.

**Symptom.** `mobile.css` loaded, `_inject_css()` ran, the sign-in page rendered normally — and *not one*
rule from the file existed in the browser. Verified via `document.styleSheets`: 519 CSS rules present,
zero of them ours.

**Root cause.** `st.html()` wraps the whole file as `<style>` + file contents + `</style>`. The file's header
comment happened to contain the literal text `<style>` (it was *documenting* that very wrapping). That stray
inner tag corrupts the block during sanitisation, and every rule in the file is discarded.

**Isolated by bisection** — three one-rule CSS files through an otherwise identical minimal app:

| Variant | Content | Rule registered? |
|---|---|---|
| A | comment containing the literal text `<style>` | **No** |
| B | ordinary comment | Yes |
| C | `:has()` selector + `@media` block | Yes (both) |

So the trigger is narrowly the literal tag text — `:has()` and `@media` are fine, which independently
validates 9b's approach.

**Fix.** Reworded the comment to say "style tags" without angle brackets, and added
`test_stylesheet_contains_no_literal_style_tag` to `tests/test_dashboard_helpers.py` asserting neither
`<style` nor `</style` appears anywhere in the file. The stylesheet itself carries a warning comment.

**Diagnostic that worked**, worth reusing: don't trust a screenshot, and don't trust
`documentElement.innerHTML` either — Streamlit's emotion CSS is inserted via CSSOM (`insertRule`), so those
rules have empty `textContent` and never appear in `innerHTML`. Enumerate `document.styleSheets` and search
`cssRules[].cssText` instead. Then bisect against a *minimal* app on a spare port: that is what separated
"app structure is wrong" from "CSS content is wrong" in two runs, after four probes down the wrong path.
>
> Mobile is a primary use case, not an afterthought: Phase 0 requires an HTTPS redirect URI specifically so
> the two allowlisted users can sign in from their phones, and verification item 15 already exercises that
> path. But nothing has ever been *designed* for a small viewport — there is no `.streamlit/config.toml`, no
> CSS of any kind, no `fig.update_layout` on any of the 12 Plotly figures, and no `column_config` sizing on
> the two widest tables.

**Decisions (2026-07-19), recorded so they are not re-litigated:**

1. **CSS ships via `st.html()` pointed at a `.css` file — never `unsafe_allow_html`.** This preserves the
   security posture recorded at the top of Phase 2.5.
2. **Same content on mobile, reflowed.** No viewport detection, no divergent layouts, no charts hidden on
   phones. One layout to build and test; a longer scroll on the Overview tab is accepted.
3. **Non-blocking.** Lands after the publish merge, unlike 1f / 2.5 / 5.

**Evidence gathered before writing this phase** (verified against the installed Streamlit 1.59.2, not
assumed — re-verify if the `streamlit` floor in `requirements.txt` moves):

- **Streamlit already stacks columns on phones.** Its frontend sets, on every column element,
  ``[`@media (max-width: ${e.breakpoints.columns})`]: { minWidth: `calc(100% - ${e.spacing.twoXL})` }``, with
  breakpoints `sm: 576px`, `columns: 640px`, `md: 768px`. Below 640px every column goes full width and stacks.
  **So the problem is not squashed metrics — it is vertical sprawl**: the 6-wide row at `app/dashboard.py:818`
  becomes six stacked cards, and the Overview tab (12 metrics + 6 charts) becomes an enormous scroll. Design
  the phase around *density*, not around reducing column counts.
- **`st.html` is a first-class CSS channel.** Per `streamlit/elements/html.py`: when `body` is a path to a
  `.css` file, Streamlit wraps the content in `<style>` tags automatically; and `_html_only_style_tags()`
  routes style-only content to the **event container**, so it consumes *zero layout space*. The default
  sanitizer path (`unsafe_allow_javascript=False`) uses `{USE_PROFILES:{html:true}}`, `style` is in
  DOMPurify's default html tag allowlist, and DOMPurify does not parse or strip CSS rule contents — so
  `@media` queries survive intact.
- **12 Plotly figures with zero layout tuning** — no `update_layout`, no margins, no legend positioning, no
  height anywhere in the repo. Plotly's default 450px height plus a default right-hand legend is what actually
  breaks charts on a phone, worst on the high-cardinality `color="category"` figures (`dashboard.py:917`,
  `1024`).
- **Two wide tables with no sizing**: `st.dataframe` at `dashboard.py:1057` renders **7 columns with no
  `column_config` at all**; the `st.data_editor` at `1090` renders 6 visible columns.
- **An 11-widget sidebar** (`_build_sidebar_filters`, def `dashboard.py:538`, plus `auth.py:172-182`),
  including three multiselects defaulting to *all options selected* and a two-handle float slider — the
  hardest widget class to operate by touch — inside a drawer that must be opened and closed for every change.

### Gotcha: module-level `st.*` calls in `app/streamlit_app.py` only run once per process

> Discovered 2026-07-26 while fixing the dashboard's full-width layout (credit-card-utilisation +
> full-width session). Read this before touching `st.set_page_config`, CSS injection, or anything else
> placed at module scope in `app/streamlit_app.py` — the failure mode is completely silent (no exception, no
> console warning) and cost most of a session to root-cause. Filed here, under Phase 9, because CSS/layout
> work is exactly where this will bite next.

**Symptom.** `layout="wide"` was already set at module scope in `app/streamlit_app.py` (this predates Phase
9) and had never actually produced a wide layout. Adding
`st.markdown("<style>...</style>", unsafe_allow_html=True)` at the same module scope to widen the block
container appeared to do nothing — not even after full server restarts, fresh OS processes (verified by
new PIDs via `Get-CimInstance Win32_Process`), and confirming the on-disk file content was correct via `Read`.

**Root cause — two independent bugs stacked on top of each other:**

1. **`st.markdown(html, unsafe_allow_html=True)` silently drops raw `<style>` tags.** Even with
   `unsafe_allow_html=True`, no `<style>` element ever appeared in the DOM and no error was raised —
   confirmed by querying `document.querySelectorAll('style')` in the live page via browser devtools/JS
   console. `st.html(...)` is the correct primitive for injecting a `<style>` block; unlike `st.markdown`,
   it is not run through the tag-stripping sanitizer. (Phase 9a below already uses `st.html()` for exactly
   this reason — it independently arrived at the right primitive. This gotcha is about *where* it's called
   from, not *which function* — see point 2.)

2. **Module-scope `st.*` calls in an *imported* module only execute on that process's first-ever script
   run — never again.** The actual script Streamlit invokes is the tiny repo-root shim (Phase 10a):
   ```python
   from app.streamlit_app import main
   if __name__ == "__main__":
       main()
   ```
   Streamlit re-executes this shim top-to-bottom on *every* rerun (every widget interaction, every new
   browser tab/session attaching to the same running process). But `from app.streamlit_app import main` is a
   plain Python import: once `app.streamlit_app` is in `sys.modules` (which happens on the very first
   import, in the very first script run of the process), every subsequent `from app.streamlit_app import
   main` is a cache hit — Python returns the already-created `main` function object and does **not**
   re-execute the module's top-level statements. Anything sitting at module scope in `app/streamlit_app.py`
   (`st.set_page_config()`, a bare `st.html(...)` call, a stray `st.write(...)`) therefore fires exactly
   once per OS process, on whichever session happens to be first to connect after a (re)start — and is
   completely absent from every other session's rendered output, forever, until the process is restarted
   again. This is *not* the same thing as Streamlit's dev-mode hot-reload-on-file-save (which reruns the
   script but does not by itself explain a *correctly-loaded* module skipping its own top-level code on a
   plain rerun) — it is ordinary CPython import caching, and it applies even to a freshly-restarted process
   the moment a second session, tab, or rerun touches it.

   Functions called every run (`render_sidebar(settings)`, `render_dashboard(...)`, anything invoked from
   inside `main()`) are unaffected — they execute fresh on every rerun because they are *called*, not
   *imported*, each time. That is why `render_sidebar`'s output (and every `dashboard.py` change made in the
   same session) rendered correctly and immediately, while the module-scope CSS fix appeared completely
   inert — two visibly different reload behaviours from two edits made minutes apart, which is what made this
   confusing to diagnose.

**The fix.** Move every Streamlit call whose effect must hold on *every* render — `st.set_page_config()`,
layout/CSS injection, anything else layout-affecting — to be the first statement(s) **inside `main()`**
itself, exactly like `render_sidebar`/`render_dashboard` already are. Current `app/streamlit_app.py`:
```python
def main() -> None:
    st.set_page_config(page_title="Automated Financial Intelligence", layout="wide")
    st.html(
        '<style>[data-testid="stMainBlockContainer"] '
        "{max-width: 100%; padding-left: 2rem; padding-right: 2rem;}</style>"
    )
    settings = load_settings()
    render_sidebar(settings)
    ...
```
`st.set_page_config()` still satisfies Streamlit's "must be the first Streamlit command" constraint here,
because it is chronologically the first `st.*` call made in every run — the shim's `from ... import main`
line is a plain import, not a Streamlit call. This pattern generalizes: **any module-level `st.*` call in
`app/streamlit_app.py` specifically (the module reached only via import, never run directly) is suspect** —
if its effect needs to appear on every render, it must live inside a function that gets called every render,
not at the top of the file.

**How this was actually diagnosed (useful if this class of bug recurs):**
- Don't trust a visual screenshot alone — confirm via the browser JS console:
  `getComputedStyle(document.querySelector('[data-testid="..."]')).<property>`, and count matching elements
  with `document.querySelectorAll(...)`.
- Rule out staleness before suspecting the mechanism: confirm the file on disk is correct (`Read`, not
  memory), and confirm a *genuinely new OS process* is bound to the port —
  `Get-NetTCPConnection -LocalPort <port> -State Listen | Select-Object -ExpandProperty OwningProcess`, then
  `Get-CimInstance Win32_Process -Filter "ProcessId=<pid>" | Select-Object CommandLine,CreationDate` — and
  that its `CreationDate` is after the file's `LastWriteTime`.
- Rule out import-path shadowing: this repo uses a PEP 660 editable install
  (`__editable__.automated_financial_intelligence-0.1.0.pth` /
  `__editable___automated_financial_intelligence_0_1_0_finder.py` in the venv's `site-packages`), which maps
  each top-level package (`app`, `core`, `database`, …) to an absolute path via a `MAPPING` dict in the
  generated finder. Worth a quick `grep` of that file if imports ever seem to resolve to the wrong copy —
  in this investigation the mapping was correct and this was ruled out, but it is a real class of bug on
  other machines/installs.
- The single most conclusive test: drop a unique literal marker (e.g. `st.write("MARKER_12345")`) at the
  exact module-scope location under suspicion. If it does not render after a confirmed-fresh restart, the
  code path never executed for that session — independent of whatever CSS/selector confusion is also in
  play. This is what actually separated "wrong selector" from "code never runs" here; without it, the two
  failure modes look identical from the outside (nothing happens, no error).
- Also checked and ruled out: Streamlit's historical per-browser "wide mode" `localStorage` override
  (`Object.entries(localStorage)` filtered for `/wide|layout|theme/i`) — not present in this codebase's
  Streamlit version. Worth checking early in any future width/layout investigation regardless, since it is
  a real override mechanism when it exists and produces an identical-looking symptom.

**Selector note (secondary, worth recording alongside the above):** Streamlit 1.59.2 emits **both** a hashed
`st-emotion-cache-*` class **and** stable literal classes matching the element's `data-testid` — e.g. the
main block container's `class` attribute is
`stMainBlockContainer block-container st-emotion-cache-1w723zb e15ve43o4`. So a bare `.block-container`
selector does work in this version. Prefer `[data-testid="stMainBlockContainer"]` attribute selectors
anyway — `data-testid` is Streamlit's explicit, documented testing/accessibility hook, while the plain
literal class name is incidental and not documented as stable across versions.

### 9a. CSS delivery mechanism (foundation — land before 9b/9e/9f)

Create `app/static/mobile.css` (new `app/static/` directory) and load it once per render.

Add to `app/dashboard.py` (requires `import pathlib` in the imports block):

```python
_MOBILE_CSS_PATH = pathlib.Path(__file__).parent / "static" / "mobile.css"


def _inject_mobile_css() -> None:
    """Load the responsive stylesheet once per render.

    st.html() wraps a .css file in <style> tags and routes style-only content to the
    event container, so this costs zero layout space. DOMPurify keeps <style> and does
    not touch rule contents, so @media queries survive — no unsafe_allow_html required
    (see Phase 2.6 for why that matters).
    """
    st.html(_MOBILE_CSS_PATH)
```

Call it as the first statement in `render_dashboard` (def `dashboard.py:1118`), before the sidebar is built —
**not** at module scope in `app/streamlit_app.py` or `app/dashboard.py`. See the "Gotcha: module-level
`st.*` calls in `app/streamlit_app.py` only run once per process" section directly above: `render_dashboard`
is called fresh on every rerun (unlike module-level code in an imported file), which is exactly why this
call site is correct as specified.

Resolve the path from `__file__`, **not** relative to the CWD. Every other path in this repo is CWD-relative
(`CLAUDE.md`), but a stylesheet must not silently vanish when the app is launched from another directory.

**Maintenance hazard to accept explicitly**: the rules below target Streamlit's `data-testid` hooks
(`stHorizontalBlock`, `stColumn`, `stMetric`, `stTabs`, `stSidebar`), which are **not a stable public API**
and may change across Streamlit upgrades. Mitigations: every rule is purely additive (delete `mobile.css` and
you are back to today's desktop-first behavior), and the stylesheet is re-verified whenever the
`streamlit>=1.41.0` floor in `requirements.txt` moves.

### 9b. KPI rows — wrap 2-up instead of 1-up (highest-leverage change)

Below 640px Streamlit forces `min-width: calc(100% - 1.8rem)` on each column. Override it for *metric-bearing*
rows only, so KPIs pair up and the Overview scroll roughly halves:

```css
@media (max-width: 640px) {
  /* Streamlit forces one-column stacking below 640px; let metric rows pair up. */
  [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) [data-testid="stColumn"] {
    min-width: calc(50% - 0.9rem) !important;
    flex: 1 1 calc(50% - 0.9rem) !important;
  }
  [data-testid="stMetricValue"] { font-size: 1.25rem; }
  [data-testid="stMetricLabel"] { font-size: 0.75rem; }
}
```

The `:has()` scoping is what keeps this safe: chart columns (`dashboard.py:444, 680, 753, 872`) keep stacking
full width, which is what charts want. Browser floor for `:has()` is Safari 15.4+ / Chrome 105+ — fine for
2026 mobile. If it ever must be dropped, wrap each metric row in an explicit `st.container()` and target that
instead.

Metric rows affected, by column count:

| Line | Section | Columns | Stacked today | After 9b |
|---|---|---|---|---|
| `dashboard.py:434` | `_section_net_worth` | 3 | 3 rows | 2 rows |
| `dashboard.py:648` | `_section_overview` | 5 | 5 rows | 3 rows |
| `dashboard.py:669` | `_section_overview` | 4 | 4 rows | 2 rows |
| `dashboard.py:818` | `_section_cash_flow` | 6 | 6 rows | 3 rows |

### 9c. Plotly — one shared layout helper applied to all 12 figures

Add alongside the other private helpers in `app/dashboard.py`:

```python
def _style_chart(fig, *, height: int = 320):
    """Apply mobile-safe layout to a Plotly figure. Call before st.plotly_chart."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=32, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="left", x=0),
        hovermode="x unified",
        autosize=True,
    )
    return fig
```

Why each setting: a horizontal legend below the plot stops high-cardinality `color="category"` legends
(`dashboard.py:917`, `1024`) from consuming half the width; tight margins reclaim ~80px on a 390px screen; an
explicit height beats Plotly's 450px default once the legend has moved below the plot area.

Wrap all 12 `st.plotly_chart` call sites — lines **460, 489, 700, 724, 770, 801, 850, 870, 891, 912, 926,
1035**. They already pass `use_container_width=True`, so only the figure object changes.

Also pass `config={"displayModeBar": False}` at each call site: the Plotly modebar is unusable by touch and
steals vertical space. Leave `scrollZoom` off (the default) so a chart never captures page scroll.

Two figures need a taller override, `height=380`: the horizontal top-categories bar (built at `691`) and the
anomaly scatter (built at `1024`).

### 9d. Tables — explicit `column_config` on both wide tables

- **`st.dataframe` at `dashboard.py:1057`** (anomalies — 7 columns, currently *zero* config): add
  `column_config` with `width="small"` on Date / Amount / Outlier score, `width="medium"` on Description, and
  a `NumberColumn(format="$%.2f")` on Amount so it stops rendering full float precision into a narrow column.
  Add an explicit `height` to cap the block.
- **`st.data_editor` at `dashboard.py:1090`** (ledger — 6 visible columns): same treatment. Keep the existing
  `column_config={"hash": None}` (`1094`) and the Category `SelectboxColumn` (`1095`) exactly as they are.

**Deliberate non-goal**: horizontal scroll *inside* a table block is acceptable on mobile. Do not hide columns
per-viewport — that would violate decision 2 above.

### 9e. Sidebar / filters — the biggest interaction cost

On mobile the sidebar is a full-screen drawer. With 11 widgets and three all-selected multiselects it is very
tall, and every filter change costs open → scroll → change → close.

- Group the secondary filters (categories, accounts, amount range, description search, outliers-only) inside a
  single `st.sidebar.expander(T["filters_more"], expanded=False)`, leaving **period** and **owners** — the two
  that actually get changed — at the top, always visible.
- Keep `_build_sidebar_filters`'s signature and return shape (`tuple[pd.DataFrame, pd.DataFrame, list[str]]`)
  unchanged so nothing downstream moves.
- The two-handle `st.sidebar.slider` amount range is the hardest widget to operate by touch. **Chosen
  (2026-07-27): replaced with two `number_input`s** (min/max), globally rather than per-viewport — see
  decision 1 above. Inverted input (min > max) is normalised via `min()`/`max()` rather than silently
  returning zero rows.
- The duplicates-only toggle (added by Phase 12, after this phase was drafted) is also secondary and went
  into the same expander.
- New `_STRINGS` key `filters_more` in **both** `en` and `fr` (Phase 8b i18n-parity rule).
- `auth.py:179` renders a raw Supabase URL as a sidebar caption — a long unbreakable token in a narrow drawer.
  Add `overflow-wrap: anywhere` for sidebar captions in `mobile.css`.

### 9f. Page config, tabs, and touch targets

- `st.set_page_config` (`app/streamlit_app.py:21`) sets only `page_title` and `layout="wide"`. Add
  `initial_sidebar_state="collapsed"` so the first paint on a phone is the dashboard, not the filter drawer.
  This is a deliberate mobile-first tradeoff — on desktop the sidebar becomes one extra click.
- 4 tabs at `dashboard.py:1158`. The **French labels are longer** ("Flux monétaires"), so the tab bar overflows
  sooner in FR. Streamlit scrolls the tab bar horizontally, which is acceptable, but add a `font-size`
  reduction for `[data-testid="stTabs"] button` inside the 640px query so all four fit without scrolling.
- Enforce a 44px minimum touch target for buttons and toggles in the mobile query (Sign out, Save budgets,
  the language toggle).
- *Optional*: add `.streamlit/config.toml` (none exists today) to pin `[theme] base` and `baseFontSize`.
  Flagged optional because it affects desktop equally.

### 9g. Verification

1. `streamlit run app/streamlit_app.py`, then Chrome DevTools device toolbar at **390×844** (iPhone 14),
   **360×800** (Android), and **768×1024** (tablet). Streamlit's 640px and 768px breakpoints sit between
   these, so all three code paths get exercised.
2. Per tab: no horizontal *page* scroll; KPI rows wrap 2-up; every chart legend sits below its plot with at
   least ~250px of plot area remaining; no clipped axis labels.
3. Transactions tab: the table scrolls horizontally *within its own block*, and the category
   `SelectboxColumn` opens and is selectable by touch.
4. Budget tab: `st.data_editor` numeric entry works with the on-screen keyboard; "Save budgets" persists.
5. Switch to French and re-check the tab bar and every metric label for truncation (FR strings are longer).
6. Real-device pass against the HTTPS deployment with both allowlisted accounts — this also re-runs
   verification item 15 (mobile sign-in).
7. `python -m unittest discover -s tests -v` still green — none of this touches classification or data logic.

---

## Phase 10 — Free hosting: dashboard on Streamlit Community Cloud

**Question that prompted this (2026-07-20):** can the dashboard *and* the pipeline both be hosted on GitHub,
for free, in one place?

**Answer: not entirely, for a structural reason.** GitHub Pages serves static files only — it cannot run a
Python process or hold the WebSocket connection Streamlit depends on. No configuration changes that. GitHub
Actions *can* run the pipeline, and already does (Phase 5). So the split is:

| Component | Runs on | Cost |
|---|---|---|
| Code, issues, CI | GitHub | Free |
| Daily pipeline (`main.py`) | GitHub Actions (`daily-finance-pipeline.yml`) | Free |
| Dashboard (Streamlit) | Streamlit Community Cloud (SCC) | Free |
| Postgres | Supabase / Neon (already in use) | Free tier |

"One place" still holds where it matters: GitHub stays the single source of truth, and SCC deploys straight
from this repo, auto-redeploying on every push to the tracked branch. Nothing is deployed by hand.

**Blocker found during research (2026-07-20).** `app/streamlit_app.py:15-17` does `from core.config import
...` and `from app.auth import ...`. That works locally *only* because the project is installed editable
(`__editable__.automated_financial_intelligence-0.1.0.pth` in the venv's site-packages). Streamlit's
launcher (`streamlit/web/bootstrap.py:59`) runs `sys.path.insert(0, os.path.dirname(main_script_path))` — it
adds the **script's own directory**, not the repo root. On SCC there is no editable install, so `app/` lands
on `sys.path`, `core` is not importable, and the app fails at import. This must be fixed regardless of host,
and it is why the commented-out `sys.path` block at `app/streamlit_app.py:5-11` exists.

### 10a. Root-level entry point (the blocker) — DONE (uncommitted)

> **Status (2026-07-20): implemented in the working tree, not yet committed.** Root `streamlit_app.py`
> exists with exactly the shim below; the dead commented-out `sys.path` block is gone from
> `app/streamlit_app.py` (ruff also re-sorted its imports in the same pass); and the run command reads
> `streamlit run streamlit_app.py` in `README.md`, `CONTRIBUTING.md`, and `CLAUDE.md`. This unblocks
> 10b–10i.

Create `streamlit_app.py` at the **repo root** — also SCC's conventional default entrypoint filename:

```python
from __future__ import annotations

from app.streamlit_app import main

if __name__ == "__main__":
    main()
```

Because the entry script now sits at the repo root, Streamlit inserts the repo root into `sys.path`, and
`core` / `app` / `database` import normally with no `sys.path` manipulation anywhere.

> **Correction (2026-07-26): the claim below (module-scope `set_page_config`) is wrong and no longer matches
> the code.** `app/streamlit_app.py` now calls `st.set_page_config()` (and any other per-run Streamlit call,
> e.g. CSS injection) as the **first statement inside `main()`**, not at module scope. Module-scope
> `st.*` calls in `app/streamlit_app.py` only execute once — on the process's first-ever script run — and
> silently no-op on every later rerun or new session. See **"Gotcha: module-level `st.*` calls in
> `app/streamlit_app.py` only run once per process"** (added under Phase 9, below) for the full mechanism,
> how it was diagnosed, and what to do instead. The paragraph immediately below is preserved for history but
> should not be followed.

> ~~`app/streamlit_app.py` keeps `st.set_page_config()` at module scope — it runs on import, before any other
> Streamlit call, which is required.~~

Same commit: delete the dead commented-out `sys.path` block at `app/streamlit_app.py:5-11`, and update the
run command to `streamlit run streamlit_app.py` in `README.md`, `CONTRIBUTING.md`, and `CLAUDE.md`.

### 10b. Dependency file and Python version on SCC

No file changes needed. SCC selects **one** dependency file, in priority order: `uv.lock` → `Pipfile` →
`environment.yml` → `requirements.txt` → `pyproject.toml`. This repo has `requirements.txt` and
`pyproject.toml`, so `requirements.txt` wins — the desired outcome. `requirements.lock` is **not** in that
list and is ignored.

Record the consequence in `docs/deployment.md`: CI and the daily pipeline install from the hash-locked
`requirements.lock` (`--require-hashes`, Phase 1f), but SCC installs the unpinned `>=` floors in
`requirements.txt`. The dashboard process holds `DATABASE_URL` and the OAuth client secret, so this is the
one place Phase 1f's supply-chain guarantee does not reach. Accepted for now; revisit if SCC adds lockfile
support.

Pin the interpreter in SCC's *Advanced settings* to **3.12** (inside the CI matrix; `pyproject.toml`
requires `>=3.12`).

### 10c. Secrets on SCC — no code change required

`core/config.py::_load_secrets_file` already reads `.streamlit/secrets.toml`, which is exactly what SCC's
secrets editor materializes. `_read_value` precedence is env → secrets → default, and SCC sets no env vars,
so the TOML is used directly. This is an existing-design win, not new work.

Keys to paste into SCC → *Settings → Secrets* (values copied by the owner from their own `.env`):

```toml
DATABASE_URL = "..."
GOOGLE_OAUTH_CLIENT_ID = "..."
GOOGLE_OAUTH_CLIENT_SECRET = "..."
GOOGLE_OAUTH_REDIRECT_URI = "https://<your-app>.streamlit.app/"
GOOGLE_ALLOWED_EMAILS = "email1@gmail.com,email2@gmail.com"
```

No `PLAID_*` key belongs here — the dashboard never ingests, `load_settings()` treats Plaid as optional, and
only `pipeline/runner.py::_build_ingestor` enforces it. Plaid credentials live in GitHub Secrets (Phase 5)
only. `.streamlit/secrets.toml` is already gitignored (`.gitignore:227`).

### 10d. OAuth redirect URI — closes the outstanding Phase 0 item

No code change: `app/auth.py:82,105` already pass `settings.google_oauth_redirect_uri` straight through.
There is a deliberate chicken-and-egg — the URL does not exist until the first deploy — so the order is:
deploy → read the assigned URL → register it in the Google console → set the secret → reboot the app.

### 10e. Branch strategy

Deploy SCC from **`main`**, not `dev`. `main` currently holds a single commit, so the existing Phase 0
"merge `dev` → `main`" item is a prerequisite. Merging serves both needs at once: it activates the Actions
cron (which only schedules from the default branch) and gives SCC a stable branch to track.

### 10f. Docs

- `README.md` — add the live app URL and a "Deployed on Streamlit Community Cloud" note under Quickstart;
  update the run command to `streamlit run streamlit_app.py`.
- `docs/deployment.md` — replace the short "Dashboard" paragraph with the full SCC walkthrough, the
  dependency-file caveat from 10b, and the caveats below.

### 10g. Caveats to document

- **Idle sleep.** SCC hibernates inactive apps; the first visit after a while takes ~30s to wake.
- **Sign-in after a restart.** The PKCE verifier lives in a module-global dict (`app/auth.py:17`,
  deliberately — see ordering constraint 14). If SCC restarts the app between redirect-out and
  redirect-back, sign-in fails with "session expired" and a retry fixes it. Already described in
  `docs/setup-google-oauth.md`.
- **Region.** SCC runs in US datacenters only. Supabase/Neon are reachable over the public internet and TLS
  is enforced by `core/config.py::enforce_tls`, so no change is needed — but the database must not be
  IP-allowlisted to a home address.
- **Sign-in opens a new tab.** SCC wraps every app in its own sandboxed iframe that blocks top-level
  navigation entirely — `target="_top"` (Phase 2.6's original fix) is silently blocked with no error. Fixed
  in Phase 2.6a via `target="_blank"`, which also means sign-in now opens a new tab locally too, not just on
  SCC. This was a real, dead-button bug found only after deploying — see Phase 2.6a for the full diagnosis.

### 10h. Owner actions (manual; no code)

1. Merge `dev` → `main` and push (Phase 0 item; prerequisite for both SCC and the cron).
2. At **share.streamlit.io**, sign in with the GitHub account owning the repo.
3. *Create app* → repo `j1cobs/automated-financial-intelligence`, branch `main`, main file path
   `streamlit_app.py`. Under *Advanced settings*, set Python to **3.12**.
4. Choose the subdomain — this fixes the URL as `https://<subdomain>.streamlit.app/`.
5. Deploy. **First boot will start but sign-in will fail** — expected; the redirect URI is not registered
   yet.
6. Google Cloud Console → *APIs & Services → Credentials → OAuth client* → add
   `https://<subdomain>.streamlit.app/` to *Authorized redirect URIs*, keeping `http://localhost:8501/` as a
   second entry for local dev. **The trailing slash must match exactly.**
7. SCC → *Settings → Secrets* → paste the 10c TOML with `GOOGLE_OAUTH_REDIRECT_URI` set to that same URL.
8. Reboot the app from the SCC menu so it picks up the new secrets.
9. Tick the Phase 0 HTTPS-redirect-URI checkbox.

### 10i. Verification — fully confirmed (2026-07-26, updated 2026-07-27), desktop and mobile

1. `streamlit run streamlit_app.py` from the repo root works locally.
2. Prove the entry-point fix is real and not masked by the editable install: in a scratch venv without
   `pip install -e .`, `streamlit run streamlit_app.py` must still start. (`streamlit run
   app/streamlit_app.py` is expected to fail with `ModuleNotFoundError: core` — that is the bug being fixed.)
3. `python -m unittest discover -s tests -v` still green — 118 tests, confirmed passing (2026-07-26).
4. **[x] Desktop, `jacosse1@gmail.com`:** the `.streamlit.app` URL renders the sign-in page, "Continue with
   Google" opens a **new tab** (Phase 2.6a — SCC's own hosting iframe blocks same-tab navigation; this
   differs from local behavior described in Phase 2.6), completes sign-in there, and reaches the dashboard.
   **[x] Confirmed (2026-07-27) — `lapointe.alexie@gmail.com`:** same flow works end-to-end on the live SCC
   deployment; the second allowlisted account signs in and reaches the dashboard. **[x] Confirmed
   (2026-07-27) — non-allowlisted account:** signing in with an email not in `GOOGLE_ALLOWED_EMAILS` was
   correctly refused on the live deployment — the allowlist fails closed end-to-end, not just locally. This
   item is now fully closed.
5. **[x] Confirmed (2026-07-27).** Mobile: same URL, sign-in works on mobile — this is the case the HTTPS
   redirect URI exists for, and it re-runs global verification item 15.
6. **[x] Confirmed 2026-07-26** — the dashboard shows the expected transaction data after signing in.
7. **[x] Done** — `dev` merged to `main` and pushed (`9f0b34d`); confirmed via
   `git merge-base --is-ancestor` that `dev`'s tip is an ancestor of `origin/main`.
8. **[x] Confirmed 2026-07-26** — sign-in genuinely completes against the **live deployed SCC URL**, not
   just locally. Phase 2.6a was found precisely because every earlier verification pass in this phase and
   Phase 2.6 only ever ran locally, where the SCC-specific iframe that broke it doesn't exist.

---

## Phase 11 — Plaid token tooling: mint and repair Items from this repo — DONE (2026-07-26), confirmed working

> **Status:** implemented and confirmed live. The user ran both `create` (sandbox) and `repair` (against a
> real broken production Item) and confirmed both worked — `repair` fixed the `NO_ACCOUNTS` failure that
> had been breaking the daily pipeline since its first run.

### Context

The daily pipeline had failed every run since its first success. The cause (see the failure log worked
through earlier this session) was a Plaid `NO_ACCOUNTS` / `ITEM_ERROR` on `accounts/get` — the Item behind
one of the production access tokens no longer had any accounts attached to it. The pipeline died at
`ingestion/plaid_ingestor.py::fetch_accounts()` before any DB logic ran.

Fixing that meant leaving this repo entirely and driving the separate `quickstart` checkout (Flask +
`plaid_python` + a React/Vite frontend) just to get a token back. That is a heavy, disconnected detour for
a recurring operational chore — and per the old `docs/setup-plaid.md`, this repo had *deliberately* had no
Link integration, so the detour was permanent by design.

**Goal:** one environment-aware CLI in this repo that both mints new Item tokens and repairs broken ones,
with no Flask, no React, no new dependencies.

Two research findings shaped the design:

| Finding | Consequence |
|---|---|
| `redirect_uri` is only required for **mobile** Plaid Link clients; desktop web OAuth works without one | No HTTPS, no self-signed cert, no Plaid Dashboard allowlisting — plain `http://localhost` works even for OAuth banks like Chase. |
| In Link **update mode** the `access_token` does not change — Plaid: "there is no need to repeat the exchange token process" | Repairing a broken Item needs **zero** GitHub Secret rotation. `update: { account_selection_enabled: true }` is Plaid's prescribed fix for `NO_ACCOUNTS`. |

| | `create` (new Item) | `repair` (update mode) |
|---|---|---|
| `/link/token/create` | `products: ["transactions"]` | `access_token: <existing>`, **no** `products` |
| After Link succeeds | exchange `public_token` → **new** access token | **no exchange**; original token stays valid |
| `.env` / Secret effect | append token (+ owner); GitHub Secret must be updated by hand | none needed |

### 11a. `ingestion/plaid_link.py` — the API surface

`PlaidLinkClient` sits beside `plaid_ingestor.py` (token lifecycle is connection management — it belongs
*next to* `PlaidIngestor`, not inside it, since that class's job is fetching transactions):

```python
class PlaidLinkClient:
    def __init__(self, client_id, secret, base_url, timeout_seconds=30): ...
    def create_link_token(self, *, access_token=None, client_name=..., country_codes=None, language="en") -> str: ...
    def exchange_public_token(self, public_token: str) -> str: ...
    def create_sandbox_public_token(self, institution_id: str, products=None) -> str: ...
    def get_item(self, access_token: str) -> dict: ...
    def get_accounts(self, access_token: str) -> dict: ...

def classify_item_status(item_response: dict, accounts_response: dict | None) -> str:
    """Reads Plaid's actual (flat) error shape: error_code sits at the top level, not
    nested under an "error" key. Returns 'OK (n accounts)' or the raw error_code."""
```

`create_link_token`'s create/update split is exact: update mode sends `access_token` + `update:
{account_selection_enabled: true}` and omits `products` entirely (Plaid rejects `products` alongside
`access_token`); create mode is the reverse. Mirrors `PlaidIngestor._post()` (same `requests.post` /
`response.ok` logging / `raise_for_status()`); no `plaid_python` dependency added.

### 11b. `scripts/plaid_link.py` — the CLI

Thin layer over 11a: `argparse`, a throwaway local Link server, prompts, `.env` writing. Logic lives in
module-level functions (`cmd_create`, `cmd_repair`, `_item_status`, `_safe_call`, `run_link_flow`, the
`.env` helpers) rather than buried in `main()`, matching how `tests/test_seed_sample_data.py` imports
`scripts.seed_sample_data` internals directly. Credentials come from `core.config.load_settings()`.

```
python scripts/plaid_link.py create --append [--owner NAME] [--print-token] [--institution ins_109508]
python scripts/plaid_link.py repair [--token-suffix 1372c4]
```

- **`create`** is environment-aware off `settings.plaid_base_url`: sandbox mints headlessly via
  `create_sandbox_public_token()` (no browser); production opens Plaid Link in the default browser and
  exchanges the result.
- **`repair`** prints every configured token with a live status (`_item_status`, via `get_item` +
  `get_accounts`), lets you pick one (or pass `--token-suffix`), runs Link in update mode, then re-calls
  `get_accounts` to confirm the Item is healthy before telling you no Secret update is needed.
- The local server (`run_link_flow`) binds `127.0.0.1` only, on an OS-assigned ephemeral port, serves the
  Link JS page on `GET /` and receives `onSuccess`/`onExit` on `POST /callback`; no `redirect_uri` is ever
  set. A 600s timeout prevents an abandoned browser tab from hanging the process forever.

### 11c. `.env` writing — fixing an inherited footgun

`pipeline/runner.py` raises `ConfigError` when `PLAID_ACCESS_TOKEN_OWNERS` is non-empty and its length
differs from `PLAID_ACCESS_TOKENS`. The old script appended to `PLAID_ACCESS_TOKENS` only, so `--append`
against a multi-owner setup could silently break that invariant and fail the *next* pipeline run.
`append_token_to_env()` keeps both lists in lockstep: it refuses to write a mismatch, prompts for an owner
when one is required, and — a bug caught by its own test suite during implementation — does **not**
backfill blank placeholder owners for pre-existing tokens when starting a fresh owners list, because
`core/config.py::_split_csv` drops empty CSV entries on read, which would silently recreate the exact
mismatch this function exists to prevent. Comments and unrelated `.env` keys are preserved untouched.

### 11d. `tests/test_plaid_link.py` — 18 tests, all passing

`unittest` + `unittest.mock`, matching the repo's existing test style. Three groups:

- `LinkTokenPayloadTests` — create vs. update mode payload shape (the regression risk with the highest
  blast radius: this is Plaid's own rejection case).
- `ItemStatusTests` — `classify_item_status` against the *actual* `NO_ACCOUNTS` payload from the original
  failure log, plus `ITEM_LOGIN_REQUIRED`, an accounts-side error, and healthy singular/plural/zero counts.
- `EnvWriterTests` — every case operates on a `tempfile.TemporaryDirectory` path, never the real `.env`:
  fresh-file append, lockstep append, refusal on a missing owner, the corrected non-backfill behavior,
  dedup of an already-present token, and preservation of comments/unrelated keys.

`python -m unittest discover -s tests -v` stayed green throughout (117 tests total after this phase).

### 11e. Removals and doc updates — DONE

- Deleted `scripts/create_sandbox_access_token.py` (absorbed by `create`), after the sandbox `create` path
  was confirmed working — the ordering constraint that gated this deletion.
- `CLAUDE.md` — Commands and Architecture sections updated to reference `scripts/plaid_link.py` and
  `ingestion/plaid_link.py`.
- `docs/setup-plaid.md` — rewritten: both Sandbox and Production sections now point at `plaid_link.py`, and
  a new "Repairing a broken Item" subsection documents the `repair` flow and why no Secret rotation follows
  it. The old line about this repo having "no Plaid Link UI" is gone — that's exactly what this phase makes
  obsolete.
- `README.md` / `docs/deployment.md` checked for stale references — none found.
- `PLAN.md`'s own historical Phase 1–10 references to the old script name are left as-is; they're records
  of decisions made in those phases, not current-state documentation.

### Verification (all run)

1. `python -m unittest tests.test_plaid_link -v` — 18/18 pass.
2. `python -m unittest discover -s tests -v` — 117/117 pass, both before and after the old script's deletion.
3. `grep -rn "create_sandbox_access_token" --include=*.py --include=*.md .` — no hits outside `PLAN.md`'s
   historical phase text.
4. Sandbox `create --append` — confirmed working by the user.
5–6. Production `repair` against the actual broken Item — confirmed working by the user; the `NO_ACCOUNTS`
   Item is healthy again.
7–8. Pipeline recovery (`python main.py`, then the daily workflow) — left to the user to confirm on the
   next scheduled or manual run.

---

## Phase 12 — Transaction identity and duplicate handling — DONE (2026-07-27)

> **Status:** implemented on `dev` and run against production. 685 → 639 transactions, 17 accounts, 0
> duplicate `external_id`s, and three consecutive `python main.py` runs that each report `0 new, 0 already
> present, 0 stale duplicates removed`. Test suite 137 → 145.
>
> **Not yet on `main`.** See "Outstanding" at the end of this phase — the daily GitHub Actions run executes
> `main.py` from `main`, which still carries the old append-only logic.

### The constraint that shapes everything below — read this first

**The user really did make four separate real `IKEA $250.00` charges on 2026-07-02**, tapping repeatedly
against a $250 contactless limit. Four rows, one account, one date, one description, one amount — all four
legitimate.

That single fact invalidates the obvious fix. Any rule of the form "two rows on the same account with the
same date, description and amount are duplicates — delete one" destroys $750 of real spending. It rules out:

- a `UNIQUE` index on `(account_key, transaction_date, description, amount)` (migration 005 had one; 010
  drops it and forbids recreating it),
- an account-scoped `transaction_hash` — `transaction_hash` is `UNIQUE`, so whatever it hashes caps the
  table at one row per that key, and IKEA×4 becomes literally unrepresentable,
- any dashboard-side or script-side auto-collapse on the natural key.

Every mechanism below was designed around this. Where a rule *is* keyed on the natural key
(`reconcile_transactions`, migration 011), it is gated by something that can tell four real taps from four
copies — Plaid's own current count, or a mask restricted to one specific double-Item account.

### The problem: three distinct duplicate mechanisms

Production had visibly duplicated transactions. Investigation found three separate causes, each needing a
different fix. Conflating them is why earlier single-shot attempts failed.

| | Mechanism | What Plaid does | Why the existing guards missed it | Fix |
|---|---|---|---|---|
| **A** | Re-attribution | Plaid moved 60 transactions between two of one owner's chequing accounts, keeping the same `transaction_id` | Every uniqueness guarantee was **account-scoped** — `transactions_natural_key` (005) and `transaction_hash` both key on `account_key`, so the same `transaction_id` under two `account_key`s collides with nothing | Migration 009 (`transactions_external_id` partial unique index) + `build_transaction_hash` keyed on `transaction_id` |
| **B** | Co-owned account, two Items | The account with mask `4102` is exposed through *both* owners' Plaid Items; **each Item issues its own `transaction_id`s** for the same real transactions | 009 sees two different `external_id`s and allows both; the account-scoped hash only absorbs the copy if it lands on the same canonical `account_key`, which a second Item does not guarantee | `PlaidIngestor.fetch_transactions` claims each real account for one token per run; migration 011 trims the already-stored copies |
| **C** | Plaid double-post | The same real transaction returned twice under two `transaction_id`s, with **no distinguishing field whatsoever** | Nothing in the payload discriminates it from a genuine repeat | Migration 012 — a user-set `is_duplicate` flag; no automatic rule can be correct |

Mechanism C was verified, not assumed. All 9 affected groups were compared field-by-field across the two
copies: `pending`, `pending_transaction_id`, `authorized_datetime`, `merchant_entity_id`, `payment_channel`
and `website` were identical in every group. **Only `transaction_id` differs.** There is no signal to
automate on — which, combined with the IKEA case, is why C ends in a manual checkbox rather than code.

### 12a. Account identity — making two views of one account merge

**`database/migrations/008_backfill_account_mask.sql`** — recovers `mask` for rows inserted before the
column existed, by parsing the `(••••NNNN)` suffix `plaid_ingestor.py` already folds into `account_name`:

```sql
UPDATE accounts
SET mask = substring(account_name from '\(•+([^)]+)\)$')
WHERE mask IS NULL
  AND account_name ~ '\(•+([^)]+)\)$';
```

End-anchored so names carrying their own parentheses (`"... (FHSA) CAD (••••JJWQ)"`) resolve to the
trailing group; idempotent, since `ensure_schema()` re-runs every migration on every call. Why it matters:
`NULL` never disqualifies a candidate in the mask veto below, so two mask-less legacy rows both stay in the
running, the `len(matches) == 1` guard bails, and the merge is *permanently* blocked. **Validated 16/16
against known masks, 0 mismatches.**

**`DatabaseClient.canonicalize_account_keys`** (`database/db.py`) — two changes to the fallback identity
used when `persistent_account_id` is unavailable:

- **`owner_name` dropped from the tuple.** It records *which connection/token revealed the account*, not who
  owns it. A jointly-held account visible through two tokens carries two different `owner_name`s, buckets
  separately, and could therefore **never** merge — exactly mechanism B. The tuple is now
  `(official_name, account_subtype, account_type)` with `mask` as a veto/preference.
- **Exact-mask preference added.** When the fallback would otherwise be ambiguous (two accounts sharing
  `official_name`/`subtype`/`type`, one with a known mask and one still `NULL` from before 008), a single
  exact mask match wins outright instead of the ambiguity guard refusing to act.

`mask` is still deliberately *not required* in the fallback, for the same NULL-never-equals reason 008
addresses from the other side.

**`ingestion/plaid_ingestor.py::_account_identity`** (new, static) — returns
`(official_name, account_subtype, account_type, mask)`, or `None` when any field is missing, because a
partial tuple cannot safely call two accounts the same. It exists so **the ingestor and the database agree
on what "the same account" means**; if the two tuples drift apart, mechanism B silently returns.

**`scripts/dedupe_accounts.py`** — the canonical row is now the one **Plaid is still syncing**, not the
oldest:

```python
group_sorted = sorted(group, key=lambda a: (a["updated_at"], a["mask"] is not None, a["created_at"]),
                      reverse=True)
canonical = group_sorted[0]
```

`upsert_plaid_accounts` bumps `updated_at` on every conflict, so an orphaned `account_key` Plaid no longer
issues stays frozen while the live one keeps advancing. The old oldest-wins rule picked the dead key as
canonical — it would have deleted the live rows and let the accounts re-fork on the very next pipeline run.

**`DatabaseClient.merge_account`** — now returns `(moved, dropped)` instead of `None`, deletes natural-key
collisions on the destination *before* the reassigning `UPDATE` (otherwise the `UPDATE` raises a unique
violation), and carries `manual_credit_limit` (migration 007) onto the canonical row when the canonical's is
`NULL`, so a user-entered credit limit is not lost with the deleted account.

**`ingestion/plaid_ingestor.py::fetch_transactions`** — ingests each real account **once per run**. Each
account identity is claimed by the first token (in `self.access_tokens` order, so the winner is
deterministic) that reveals it; every later token's `account_id` for that identity goes into
`skipped_account_ids` and its transactions are dropped at the page loop. Accounts whose identity tuple is
incomplete are always ingested, never skipped — a partial identity is not enough evidence to discard data.
This is the fix that stops mechanism B at the source; 011 only cleans up what it already produced.

### 12b. Transaction identity — `transaction_id` as the hash input

**`build_transaction_hash`** (`database/db.py`) now keys on Plaid's `transaction_id` when there is one, and
falls back to the account-scoped formula only when there isn't:

```python
external_id = transaction.get("external_id") or transaction.get("transaction_id")
if external_id:
    return hashlib.sha256(f"plaid_txn|{external_id}".encode()).hexdigest()
identity = "|".join([account_key, _canonical_date(date), description, _canonical_amount(amount)])
```

Three consequences:

1. **The table can now hold IKEA×4.** Four real charges have four `transaction_id`s, four hashes, four rows.
   The account-scoped formula could hold one.
2. **The hash is stable across Plaid mutating a transaction.** The pending→posted transition revises
   `amount`, `date` and `description`; re-attribution changes `account_key`. Under the old formula all four
   changed the hash and produced a twin. Now they collide on the unchanged hash and `ON CONFLICT` updates
   the row in place, so `user_category`, `is_recurring` and `created_at` survive.
3. **What it does *not* catch** is a *re-issued* `transaction_id` (Item re-link, or mechanism B's second
   Item). That class is handled outside the schema, by `reconcile_transactions`.

Rows with no `transaction_id` (seed data, any future non-Plaid source) keep the account-scoped formula —
the best identity available for them.

> **This is the third sanctioned change to the hash formula under the Phase 2.7 amendment** (after 2.7's
> `account_name`→`account_key` and 2.8's type-canonicalization). It ships with `rehash_transactions()`, as
> that amendment requires: never a silent formula swap. `rehash_transactions` gained a prior pass that
> collapses rows sharing an `external_id`, keeping the newest by `(created_at, id)` — Plaid's current
> attribution, matching migration 009.

**`database/migrations/009_transaction_external_id_identity.sql`** — retires stale attributions
(`DELETE ... USING` keeping the newest per `external_id`), then enforces it going forward:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS transactions_external_id
    ON transactions (external_id) WHERE external_id IS NOT NULL;
```

Partial, because rows without an `external_id` must remain unconstrained. `external_id` is
account-independent, so this is the one index that catches mechanism A, which no account-identity heuristic
can see.

**`database/migrations/010_drop_account_scoped_natural_key.sql`** — `DROP INDEX IF EXISTS
transactions_natural_key`, permanently. The file's comment records the IKEA case as the reason so nobody
re-adds it.

**`database/migrations/005_transaction_natural_key.sql` neutered to `SELECT 1;`** — the file is *kept, not
deleted*. `ensure_schema()` re-runs every migration on every call, so leaving the original `CREATE` in place
would re-create an index that 010 immediately drops — and on this data the `CREATE` now fails outright with
a `UniqueViolation` before 010 ever runs. The header comment explains both ways 005's guarantee turned out
to be wrong.

**`database/migrations/011_trim_stale_duplicates.sql`** — a one-off, deliberately narrow trim of the
mechanism-B backlog: for accounts with `a.mask = '4102'` only, delete later copies sharing
`(account_key, transaction_date, description, amount)`. Scope is restricted to the double-Item account
precisely because that shape is *frequently real spending* elsewhere in the table. Written to be idempotent
(once the later copies are gone it matches nothing) since `ensure_schema()` re-runs it forever.

### 12c. `DatabaseClient.reconcile_transactions` (new) — the only mechanism with enough information

Called from `pipeline/runner.py` **after** `upsert_transactions`, on the frame whose `account_key`s have
already been remapped through `key_remap`:

```python
inserted, updated = database.upsert_transactions(transactions)
removed = database.reconcile_transactions(transactions, start_date, end_date)
```

The discriminator no index can have: **how many copies does Plaid itself currently return for this natural
key?** Five stored IKEA rows against four fetched means exactly one is spurious; four against four means
nothing is.

Three properties, in order of importance:

1. **A natural key Plaid returns *zero* of is skipped outright and never touched.** Plaid's transaction
   window rolls forward and drops history the database legitimately still holds (`ANTHROPIC* CLAUDE SUB
   32.19`, and others). Absence from the fetch is not evidence of duplication. This is the single most
   important safety property in the method.
2. **Deletion order**, most-expendable last, via `rows.sort(key=lambda r: (r[0], not r[1], r[2], r[3]))`:
   - user-flagged `is_duplicate` rows first — already judged expendable, so trimming must never remove
     their unflagged twin and leave the flagged copy behind;
   - then rows whose `external_id` Plaid **no longer returns**, ahead of ones it still does;
   - then earliest `(created_at, id)`, so `user_category` / `is_recurring` / `created_at` survive.
3. **Both sides are compared through `_canonical_amount` / `_canonical_date`.** The frame carries Python
   floats and `date`/`Timestamp`; Postgres returns `Decimal` and `date`. That exact mismatch already caused
   a duplicate-insert bug once (Phase 2.8) and is not allowed to recur here.

Returns the number of rows deleted, which `runner.py` logs as `%s stale duplicates removed`.

### 12d. Mechanism C — the manual `Duplicate` flag

No automatic rule can be correct in both directions, so this records the user's judgement.

- **`database/migrations/012_transaction_is_duplicate.sql`** —
  `ALTER TABLE transactions ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT FALSE;`
- **`DatabaseClient.update_transaction_duplicate(transaction_hash, is_duplicate)`** — sets the flag and
  bumps `updated_at`. The row is **retained, never deleted**, so the call is always reversible.
- **`app/dashboard.py::_section_ledger`** — a `Duplicate` / `Doublon` `CheckboxColumn` in the ledger's
  `st.data_editor`, alongside the existing category dropdown and `Recurring` checkbox, wired through the
  same edited-rows dispatch (`col_changes[T["col_duplicate"]] → db.update_transaction_duplicate(...)`).
- **`_build_sidebar_filters`** — a **"Possible duplicates only"** toggle narrowing the view to rows sharing
  `(account_key, date, description, amount)` with at least one other row, i.e. exactly the candidates worth
  inspecting by hand. Grouped on `account_key`, not `account_name`, so two distinct accounts with the same
  display name don't collapse together.
- **`load_financial_data`** selects `t.is_duplicate`; flagged rows are then excluded from analytics
  (`enriched = filtered[~filtered["is_duplicate"].fillna(False).astype(bool)]`, and the same on
  `all_time_filtered`) while remaining visible in the ledger.
- **The flag survives pipeline runs** by the Appendix-A "pipeline never writes it" rule that `user_category`
  and `is_recurring` already follow: `upsert_transactions`' `INSERT ... ON CONFLICT` **never names the
  `is_duplicate` column**, in either the column list or the `DO UPDATE SET` clause.

### 12e. Dashboard changes that came out of the same investigation

- **Manual credit limits** (`database/migrations/007_manual_credit_limit.sql`, `set_manual_credit_limit`,
  `_effective_credit_limit`) — for cards where the institution never gives Plaid a `balances.limit`.
  Deliberately a separate column from `balance_limit`, which `upsert_plaid_accounts` overwrites every run;
  Plaid's value takes precedence when present, and the UI labels a manual one as such.
- **Stale-balance warning** — accounts whose `accounts.updated_at` is older than `_STALE_BALANCE_DAYS` are
  surfaced as `st.warning` with a per-account age in days ("Re-run the pipeline or repair the Plaid
  connection"). `set_manual_credit_limit` deliberately does *not* touch `updated_at`, so a manual edit can't
  fake balance freshness.
- **Duplicate-account warning** — groups `accounts` on `(official_name, account_subtype, account_type,
  mask)` and warns when any group has more than one `account_key`, pointing at
  `scripts/dedupe_accounts.py`. The account fork that caused mechanism A was invisible for weeks; this makes
  the next one visible on the first page load.

Both warning strings exist in `en` and `fr`, per the dashboard's existing `T` dictionary convention.

### Gotcha: three dead ends, each of which cost real time

> Recorded the way the Phase 9 module-level-`st.*` gotcha is: these are not hypotheticals, they happened in
> this repo, against this database, and a future reader who skips this section will repeat at least one of
> them. One of them destroyed production data.

**1. An account-scoped `transaction_hash` was tried and reverted.** It looks correct — it is what 2.7 and
2.8 converged on, and it is what the docstring described for weeks. But `transaction_hash` is `UNIQUE`, so
it caps the table at exactly one row per `(account_key, date, description, amount)`. IKEA×4 is
unrepresentable under it; three of the four real charges vanish silently at insert time, with no error, no
log line, and a plausible-looking row left behind. The same reasoning kills migration 005's index — the two
failures are the same failure wearing different clothes. If a future change makes the hash account-scoped
again, it *will* silently delete real spending.

**2. A too-loose collision `DELETE` inside `upsert_transactions` destroyed two legitimate production rows.**
While the hash was still account-scoped, `upsert_transactions` carried a pre-insert "relocation" step: for
each incoming row with an `external_id`, if the incoming natural key was already occupied by a different
row, delete the stale row holding our `external_id`. The implementation deleted the **destination** row
rather than the stale source. Two real rows went with it — `$0.00 Fixed monthly fees` on ••••9105, dated
**2026-05-15** and **2026-07-17** — and they are **unrecoverable**: Plaid's window had already rolled past
them, so no re-ingest brings them back. The relocation step was removed **entirely** once the hash became
`transaction_id`-stable, because a stable hash makes it unnecessary: a revised or re-attributed transaction
now arrives with an unchanged hash and is absorbed by `ON CONFLICT`. The lesson is narrower than "be
careful": *any* `DELETE` inside the write path operates on rows that may be the only surviving copy of real
history, and this repo has already proven it will not notice for weeks.

**3. Reconciliation initially thrashed 43-in / 43-out on every run.** The first version of
`reconcile_transactions` sorted purely by `created_at` and kept the *earliest* row. But the earliest row is
the **stale** copy — the one carrying the obsolete `transaction_id` — while the freshly-ingested row
carrying the `transaction_id` Plaid actually returns is the newest. So every run deleted the current row,
kept the dead one, and the next run re-inserted the current row: 43 inserted, 43 deleted, forever, with the
pipeline reporting apparently-plausible non-zero numbers both ways. Fixed by making "does Plaid still return
this `external_id`?" outrank `created_at` in the sort key (the `not r[1]` term). **A pipeline that reports
steady non-zero insert *and* delete counts on an unchanged account is thrashing, not working** — the
idempotency check below exists to catch exactly this.

### Results

| | Before | After |
|---|---|---|
| Transactions | 685 | **639** |
| Accounts | (forked) | **17** |
| Duplicate `external_id`s | present | **0** |
| Pipeline idempotency | 43 in / 43 out per run | **0 new, 0 deleted** across 3 consecutive runs |
| Tests | 137 | **145** |

The 8 new tests are in `tests/test_account_identity.py`: `CanonicalizeAccountKeysTests` (exact-mask
preference, matching across differing `owner_name`, refusing to guess between ambiguous NULL-mask
candidates), `GroupDuplicatesTests` (partitioning by mask while ignoring owner), `MergeAccountTests`
(collision drop before reassign), `UpsertTransactionsExternalIdTests` (hash keys on `transaction_id`; falls
back without one; **repeated transactions each persist** — the IKEA guard), `ReconcileTransactionsTests`
(trims the stale copy not the current one; flagged duplicate deleted before its twin; genuinely repeated
transactions untouched; a key Plaid returns zero of is never deleted; float/Decimal amounts bucket
together), `DuplicateFlagTests` (flag written; **`upsert` never writes `is_duplicate`**), and
`RehashExternalIdPassTests`.

### Verification (all run)

1. `python -m unittest discover -s tests` — **145/145 pass**.
2. `python -m unittest tests.test_account_identity -v` — all pass, including the two regression guards that
   encode this phase's hard-won rules (`test_repeated_transactions_each_persist`,
   `test_key_plaid_no_longer_returns_is_never_deleted`).
3. **IKEA regression check** — `SELECT count(*) FROM transactions t JOIN accounts a USING (account_key)
   WHERE t.transaction_date = '2026-07-02' AND t.description ILIKE 'IKEA%' AND t.amount = 250.00` returns
   **exactly 4**. Re-run this after *any* change to `build_transaction_hash`,
   `reconcile_transactions`, `merge_account`, or the migration set. If it ever returns fewer than 4, real
   spending has been deleted.
4. **Plaid-dropped-history check** — transactions outside Plaid's current window are still present
   (`ANTHROPIC* CLAUDE SUB 32.19` and the other aged-out rows). Proves `reconcile_transactions`' zero-fetch
   skip is holding; a regression here deletes real history on every run.
5. **Idempotency** — three consecutive `python main.py` runs, each logging `0 new transactions, N already
   present, 0 stale duplicates removed`. Non-zero on both insert *and* delete means dead end 3 has returned.
6. **Duplicate-`external_id` check** — `SELECT external_id, count(*) FROM transactions WHERE external_id IS
   NOT NULL GROUP BY 1 HAVING count(*) > 1` returns no rows; `transactions_external_id` exists as a partial
   unique index.
7. **Account count** — 17 accounts, and the dashboard's duplicate-account warning does not fire.
8. **Flag survives a pipeline run** — tick `Duplicate` on a row in the ledger, run `python main.py`, reload
   the dashboard: the tick is still there, the row is still excluded from every total and chart, and the row
   itself was not deleted. Same check as Appendix A verification item 19, applied to `is_duplicate`.
9. **Mask backfill** — 16/16 accounts resolved to their known mask, 0 mismatches, 0 rows left with a
   parseable `account_name` but a `NULL` mask.
10. **`ensure_schema()` re-run** — calling it twice in a row is clean: 005 is a no-op `SELECT 1`, 010's
    `DROP INDEX IF EXISTS` and 011's scoped `DELETE` both match nothing the second time, 012 is
    `ADD COLUMN IF NOT EXISTS`.

### Outstanding

- ~~This work is uncommitted on `dev`.~~ **Resolved 2026-07-27**: `dev → main` merged; `origin/main` is now
  at `7379d4f` ("fix(db): deduplicate transactions + fix ui") with `dev` confirmed an ancestor via `git
  merge-base --is-ancestor`. The daily GitHub Actions cron now runs the corrected logic — Phase 12 is fully
  closed out.
- Migrations 011 (and, once its work is done, 008) are one-off cleanups that live permanently in the
  `ensure_schema()` loop. Both are idempotent, so this is correct but not free — worth a pass if the
  migration list grows further.
- `upsert_transactions`' docstring still describes the pre-Phase-12 account-scoped hash and its removed
  relocation pass in places, while the inline comment immediately below it describes current behaviour.
  Source-level cleanup, not a plan item.

---

## Phase 13 — Purge accidental seed data + seed-script guardrails — DONE (2026-08-22)

> **Status:** `purge_sample_data.py`, the guardrails, and their tests are implemented and merged on
> `dev` (165 tests green). **Run against the affected production database on 2026-08-22** — user
> confirmed the sample/demo accounts are gone from the live database. Triggered by
> `scripts/seed_sample_data.py` having been run once against production by mistake.

### What happened, and why it was recoverable

`scripts/seed_sample_data.py` was run with `DATABASE_URL` pointed at production (real Plaid data)
instead of a local/disposable database. No real rows were damaged: every write the seed makes is
namespaced and cannot collide with a real row —

| What | Seed value | Real Plaid value |
|---|---|---|
| `accounts.account_key` | `sample:Alex Chequing`, … | Plaid `account_id`-derived |
| `accounts.source` | `"sample"` — the only writer of that literal in the repo | `"plaid"` |
| `transactions.external_id` | `SAMPLE-00000`… | Plaid `transaction_id` |
| `transactions.transaction_hash` | `sha256("plaid_txn\|SAMPLE-000NN")` | hash of the real txn id |

`upsert_plaid_accounts` conflicts on `account_key`, `upsert_transactions` on `transaction_hash` — so
the damage was purely additive. It was also self-perpetuating: `reconcile_transactions` (Phase 12)
deliberately skips natural keys Plaid returns zero of, so the daily pipeline would never have
cleaned these rows up on its own.

### Fix 1 — `scripts/purge_sample_data.py` (new)

Dry-run by default, `--apply` to delete — same convention as `scripts/dedupe_accounts.py`. Backed by
three new `DatabaseClient` methods in `database/db.py`:

- `count_by_source()` — `{source: {"accounts": n, "transactions": m}}`, used to report the
  surviving non-sample totals so the operator can eyeball that real history is untouched.
- `accounts_for_source(source)` — per-account breakdown for the dry-run report.
- `purge_source(source)` — deletes transactions (via a subquery on `accounts.source`), then
  accounts, in one connection/commit. Raises `ValueError` on an empty source; hardcoded in the
  script to `"sample"` — there is no `--source` flag, so this can't become a general delete tool.

Seeded `categories` rows are left alone: all 11 the seed uses are canonical entries already seeded
by migration 003, so deleting them would break the category picker for real transactions.

### Fix 2 — guardrails on `seed_sample_data.py`

Two independent layers, since either one failing alone should not be enough to repeat this:

1. **`SEED_DATABASE_URL`, not `DATABASE_URL`.** New optional `Settings.seed_database_url` field in
   `core/config.py`, TLS-enforced like `database_url` when set. The seed script reads only this var;
   if unset, it logs an explanation and exits 1 *before constructing a `DatabaseClient`* — so a bare
   `.env` copied from prod (which has `DATABASE_URL` but not `SEED_DATABASE_URL`) fails closed
   instead of silently seeding prod. This also keeps `ensure_schema()` (which re-runs every
   migration, including the 011 DELETE) off prod's path by construction.
2. **Refuse a database that already holds real rows.** Defense in depth for the case where
   `SEED_DATABASE_URL` is itself misconfigured. After `ensure_schema()`, `count_by_source()` sums
   every non-`"sample"` source; if non-zero, the script logs the counts and the **target host only**
   (never the DSN — it has a password) and exits 1. `--force` overrides, explicit and env-var-free.

`.env.example` gained a `SEED_DATABASE_URL` block pointed at the same local docker instance as
`DATABASE_URL`, with a comment warning not to point it at production.

### Tests

- `tests/test_seed_sample_data.py` — new cases: no `seed_database_url` → exit 1, `DatabaseClient`
  never constructed; non-sample rows present → exit 1, no writes; same + `--force` → writes proceed;
  only sample rows present → writes proceed.
- `tests/test_purge_sample_data.py` (new) — no sample data is a no-op; dry run issues no delete;
  `--apply` calls `purge_source("sample")`.
- `tests/test_db_upserts.py` — `count_by_source`, `accounts_for_source`, `purge_source` (delete
  order: transactions before accounts, per the `account_key` FK; empty-source `ValueError`).
- `tests/test_config.py` — `SEED_DATABASE_URL` absent → `None`; present → TLS-enforced for remote
  hosts, untouched for localhost.

Full suite: 165 tests, all green (`python -m unittest discover -s tests -v`).

### Verification performed vs. outstanding

Done:
- Full test suite green (165 tests) after adding the new coverage listed above.
- Code review of `purge_source`'s DELETE ordering (transactions before accounts, per the
  `account_key` FK) and of the guardrail logic in `seed_sample_data.py::main()`.
- **2026-08-22:** `python scripts/purge_sample_data.py --apply` run against production — user
  confirmed the demo/sample accounts are gone and real accounts/balances are unaffected. Phase 13 is
  fully closed.

Remaining discipline (not a task, an ongoing rule): confirm `SEED_DATABASE_URL` is set locally (not
to prod) before ever running `seed_sample_data.py` again.

---

## Phase 14 — Stop logging financial data to GitHub Actions; log runs to Postgres instead — DONE (2026-08-22)

> **Status:** implemented on `dev` through Follow-ups 1–3, full test suite green (179 tests as of the
> last recorded run), and committed as `d9e1a9f` ("fix(pipeline): replace duplicate-account-skip log
> with a count, scrub tracebacks, add trigger_type"). Triggered by a request to make sure no
> transaction-level data can ever reach the GitHub Actions run log, which is visible to anyone with
> repo read access (public, if the repo is public). **Live-run verification confirmed 2026-08-22** —
> a real run showed the expected `pipeline_runs` row with no leaked data. Phase 14 is fully closed.

### What the audit found

The pipeline code path GitHub Actions actually runs (`main.py` → `pipeline/runner.py::main()`)
already logged only counts, dates, and hashes — no `description`, `amount`, or `category` value
was ever logged. Two real leak vectors existed in `ingestion/plaid_ingestor.py`, both reachable
from the scheduled run:

1. `_post()` logged Plaid's full raw HTTP error response body (`response.text`) unscrubbed on any
   non-2xx response.
2. The duplicate-account skip path logged the Plaid account mask (last-4 digits).

### Fix 1 — scrub the two leak vectors in `ingestion/plaid_ingestor.py`

- `_post()` now logs only `status_code`, `error_type`, and `error_code` parsed from Plaid's JSON
  error body (falling back to a plain status-code message if the body isn't JSON) — never the raw
  body.
- The duplicate-account skip log no longer includes the account mask; `account_id` and the token
  suffix (`token[-6:]`, the pattern already used everywhere else in this file) are enough to debug
  which account was skipped.

### Fix 2 — `pipeline_runs` table replaces per-run detail in the GH Actions log

New `database/migrations/013_pipeline_runs.sql`: `pipeline_runs(id, started_at, finished_at,
status, transactions_inserted, transactions_updated, stale_duplicates_removed, error_class,
error_message)`, no FK (a run row must be insertable even if the run failed before touching
`accounts`/`transactions`). New `DatabaseClient.log_pipeline_run(...)` in `database/db.py`, same
connect/commit shape as every other method.

`pipeline/runner.py::main()` now records `started_at`, calls `run_pipeline()` (which returns a new
`PipelineResult` NamedTuple — `transactions, inserted, updated, removed` — instead of a bare
DataFrame), and on every exit path — success, `psycopg.OperationalError`, or any other exception —
writes one row to `pipeline_runs` before returning/raising. `OperationalError` logs `error_class`
only (no message — connection errors can embed the DSN); any other exception logs `error_class`
plus `str(error)[:500]`, truncated defensively. `run_pipeline()`'s per-stage `LOGGER.info` calls
were removed; `main()` now prints a single terminal `Pipeline run: success`/`failed` line, so the
GitHub Actions log is pass/fail only (plus, on a Plaid API failure, the scrubbed error line from
Fix 1). A `ConfigError` raised before `DatabaseClient` construction (e.g. missing `DATABASE_URL`)
has nothing to log into, so it skips `log_pipeline_run` and falls straight through to
`LOGGER.exception`/re-raise.

### Tests

- `tests/test_pipeline_runner.py` — `RunPipelineTests` updated for the `PipelineResult` return
  shape; new `MainTests` covering all four `main()` exit paths (success, `OperationalError`, generic
  exception, `ConfigError` before `DatabaseClient` construction) and asserting exactly what
  `log_pipeline_run` was/wasn't called with on each.
- `tests/test_db_upserts.py` — new `LogPipelineRunTests` for the INSERT and bound params, including
  that omitted optional fields bind as `None`.
- `tests/test_plaid_ingestor.py` (new file — no prior test coverage existed for this module) —
  covers the scrubbed `_post()` error log (JSON and non-JSON bodies) and the mask-free
  duplicate-account skip log.

Full suite: 174 tests, all green (`python -m unittest discover -s tests -v`).

### Docs

`CLAUDE.md` updated: the `ingestion/` bullet notes the scrubbed Plaid error logging standard; the
`database/` bullet documents `pipeline_runs` (migration count 001–013) as where per-run detail now
lives instead of the GitHub Actions log.

### Verification performed vs. outstanding

Done:
- Full test suite green (174 tests) after adding the new coverage listed above.
- `import pipeline.runner, database.db, ingestion.plaid_ingestor` sanity-checked with no errors.

Outstanding (requires a live database / a real GitHub Actions run):
1. Run `python main.py` locally against a disposable/local database (not prod — see the
   `SEED_DATABASE_URL` guardrail rationale in Phase 13 for why) and confirm a `pipeline_runs` row
   lands with the right counts and `status='success'`.
2. Force a failure path (bad `DATABASE_URL` for the `OperationalError` branch, or a bad Plaid token
   for a `requests.RequestException`) and confirm: (a) `pipeline_runs` gets a `status='failed'` row
   with a non-transaction error message, and (b) stdout shows no response body/mask.
3. ~~Manually trigger the GitHub Actions workflow~~ — **done**, via the real daily cron run on
   2026-08-09 after merging to `main`. Result: **partial failure**, see follow-up below.

### Follow-up (2026-08-09) — two log lines in `database/db.py` still reached the log

The real production run confirmed Phase 14 was incomplete. `main`'s daily run produced:

```
2026-08-09 07:56:02,455 | INFO | database.db | Upserted 274 transactions (8 new, 266 already present)
2026-08-09 07:56:02,519 | INFO | database.db | Reconciled transactions against Plaid counts for 2026-05-11..2026-08-09: deleted 3 duplicate rows
2026-08-09 07:56:02,580 | INFO | pipeline.runner | Pipeline run: success
```

Root cause: `pipeline/runner.py`'s per-stage logging was removed as planned, but two `LOGGER.info`
calls inside `database/db.py` (`reconcile_transactions()`, `upsert_transactions()`) were
deliberately left in place at the time, since the original audit judged their content non-sensitive
(counts and a date range, no transaction data). That judgment about *content* was right, but missed
the actual goal — these calls use the `database.db` logger, which propagates to the same root
logger `pipeline/runner.py::main()` configures via `logging.basicConfig`, so they still landed in
the GitHub Actions log. Confirmed via `grep` these were the only two `LOGGER.*` calls in the file.

Fix: deleted both log calls outright rather than relocating them — their counts are already
captured with zero information loss. `run_pipeline()` already returns them via `PipelineResult`,
and `main()` already writes them into `pipeline_runs`; the only other caller,
`scripts/seed_sample_data.py`, already prints its own summary from the same returned tuple. No
signature or return-value changes, so no caller needed updating. Full suite re-run: 174 tests green,
`ruff check` clean. Live-run confirmation (merge to `main`, next scheduled/`workflow_dispatch` run
showing pass/fail only) is still outstanding.

### Follow-up 2 (2026-08-09) — duplicate-account-skip log replaced with a DB count; traceback leaks closed

A live run also surfaced a third leftover log line:

```
2026-08-09 13:35:35,155 | INFO | ingestion.plaid_ingestor | Skipping duplicate Plaid account (account_id=VNvKbJPe3pCywJ5jQ85oiPgBKyaVgOHaL9gYe) for token suffix=fa17bf; already ingested via account_id=NYvoPXBEpJC9yPAeQ9ANixYo7EX9VPU5VvxrP from an earlier token
```

Unlike Follow-up 1, the user asked for this one to get a **database replacement**, not just be
deleted — and asked for every previously-deleted log line in this effort to be re-verified against
its DB equivalent before moving on. Audit result:

| Removed log | DB replacement | Status |
|---|---|---|
| `database/db.py::reconcile_transactions()` "Reconciled transactions..." | `pipeline_runs.stale_duplicates_removed` | ✅ verified |
| `database/db.py::upsert_transactions()` "Upserted %s transactions..." | `pipeline_runs.transactions_inserted` / `.transactions_updated` | ✅ verified |
| `pipeline/runner.py` original per-stage logs | Same `pipeline_runs` row (`started_at` + the count columns above) | ✅ verified |
| `ingestion/plaid_ingestor.py` "Skipping duplicate Plaid account..." | `pipeline_runs.duplicate_accounts_skipped` (new) | Fixed below |

Fix: `database/migrations/014_pipeline_runs_duplicate_accounts.sql` adds
`duplicate_accounts_skipped INTEGER` to `pipeline_runs`. `PlaidIngestor.fetch_transactions()` no
longer logs each skip — it increments a counter and now returns `IngestResult(transactions,
duplicate_accounts_skipped)` (moved to `ingestion/base.py` since it's an interface-level type,
`BaseIngestor.fetch_transactions`'s abstract signature updated to match).
`pipeline.runner.PipelineResult` gained a `duplicate_accounts_skipped` field threaded through both
`run_pipeline()` return points; `main()` passes it to `log_pipeline_run(...)`.

While auditing, three more log statements were found that print full exception tracebacks
(`LOGGER.exception`, which includes `exc_info`) to the same stdout — never explicitly "deleted"
before, but the same category of leak. User asked to fold in a fix: swapped all three to
`LOGGER.error(..., type(error).__name__)` (matching the existing `OperationalError` pattern),
dropping the traceback while `pipeline_runs.error_class`/`.error_message` keep the full detail:
`pipeline/runner.py::main()`'s generic-exception handler, `PlaidIngestor.fetch_accounts()`, and
`PlaidIngestor.fetch_transactions()`'s page-request loop. All three still re-raise unchanged.

Tests: `tests/test_plaid_ingestor.py::DuplicateAccountSkipCountTests` (replaces the old
log-assertion test) asserts the returned count and that `LOGGER.info` is never called;
`RequestFailureLoggingTests` (new) covers both scrubbed request-failure logs; `test_pipeline_runner.py`
updated for the new `IngestResult`/`PipelineResult` shapes and the `LOGGER.error`-not-`.exception`
assertion; `test_db_upserts.py::LogPipelineRunTests` updated for the 8-column INSERT. Full suite:
176 tests green, `ruff check` clean. Live-run confirmation still outstanding.

### Follow-up 3 (2026-08-09) — two same-day `pipeline_runs` rows explained; `trigger_type` added; schedule pinned to 05:00 UTC

User noticed two `pipeline_runs` rows on the same day and asked for a code-level investigation
before accepting "probably two triggers" as the answer. Audit performed: re-read `main()` in full
(exactly one `log_pipeline_run` call per mutually-exclusive branch, no loop/retry); confirmed
`tenacity` in `requirements.lock` is only a transitive `streamlit` dependency, never imported by
this codebase; read the full git history of `daily-finance-pipeline.yml` (4 commits) — always
exactly one `schedule:` entry, no second workflow ever ran `python main.py`
(`.github/workflows/ci.yml` is test/lint-only). No code-level double-write path exists. **User
confirmed the cause**: a manual `workflow_dispatch` run (triggered earlier in this session to test
the Phase 14 fix) landed on the same calendar day as the scheduled cron run — two real, correct
executions of the pipeline, not a bug. `concurrency: { group: daily-pipeline, cancel-in-progress:
false }` means overlapping triggers queue and both still run to completion, reinforcing that two
same-day triggers reliably produce two rows.

Fix: added `trigger_type` to `pipeline_runs` (`database/migrations/015_pipeline_runs_trigger_type.sql`),
storing GitHub's own event-name vocabulary directly — `"schedule"`, `"workflow_dispatch"`, or
`"local"` for a run started outside GitHub Actions. The workflow now passes `GITHUB_EVENT_NAME: ${{
github.event_name }}` to the pipeline step; `core/config.py::Settings` gained an optional
`github_event_name` field (same pattern as the Plaid vars — absent is fine, e.g. for local runs);
`database/db.py::log_pipeline_run` and all three call sites in `pipeline/runner.py::main()` (success,
`OperationalError`, generic exception) now pass `trigger_type=settings.github_event_name or "local"`,
so a failed run is just as attributable as a successful one. Also pinned the daily cron from `0 7 * *
*` to `0 5 * * *` (05:00 UTC) per the user's request for a fixed daily time — noting GitHub Actions
schedules are documented as best-effort and may be delayed under platform load, which no code change
can guarantee around.

Tests: `test_config.py` covers `github_event_name` absent/present; `test_db_upserts.py::LogPipelineRunTests`
updated for the 9-column INSERT; `test_pipeline_runner.py::MainTests` extended with a
`trigger_type="workflow_dispatch"` case, a `trigger_type` default-to-`"local"` case, and `"schedule"`
on both failure paths. Full suite: 179 tests green, `ruff check` clean. Live-run confirmation (one
`workflow_dispatch` row showing `trigger_type='workflow_dispatch'`, one cron row showing
`trigger_type='schedule'`) still outstanding.

---

## Phase 15 — React dashboard: metric correctness, feature parity, and a real UX — IMPLEMENTED (2026-08-24), live verification outstanding

> **Status (2026-08-24):** Fixes 1-15 are implemented on `dev` across six commits. Automated
> verification is green — **283 Python tests** (`python -m unittest discover -s tests`, ruff check +
> format clean) and **216 web tests** (`npm run test`, `tsc -b`, `npm run lint` at 0 errors,
> `format:check`, `npm run build`). The Streamlit freeze held: `app/dashboard.py`,
> `tests/test_dashboard_classify.py` and `tests/test_dashboard_helpers.py` are untouched across
> every Phase 15 commit (`git log 2411582..HEAD -- app/` is empty).
>
> **What remains is the end-to-end pass in "Verification" below**, which needs a signed-in session
> against the live database and cannot be done from tests: the nine on-screen checks, the
> keyboard-only tooltip pass at a narrow viewport, the dark-mode sweep, and the side-by-side diff
> against `streamlit run streamlit_app.py` confirming **only** the five tabulated divergences.
>
> Two items were deliberately not built, both recorded at their fix below: **ledger virtualization**
> (needs a new dependency — `@tanstack/react-virtual` is the recommendation) and **metric
> drill-down** (designed for via `MetricTile`'s unused `onDrillDown` prop, so it is additive). Both
> were subsequently implemented in Phase 16 (items 8 and 9) — see that phase for what shipped.
>
> Two plan items changed during implementation and are documented where they landed:
> **(a)** Fix 7's dual-axis rolling-spend chart was collapsed to a single axis — `daily_avg` is
> `amount / 30`, so the second series drew the identical curve at 1/30 scale against an invented
> scale; the per-day figure moved into the tooltip. **(b)** Fix 15's "push the date window into SQL"
> was not possible without editing the frozen `load_financial_data`, so it shipped as the 60-second
> TTL cache in `api/dataload.py` only. If read latency ever justifies more, relocate
> `load_financial_data` into `database/` rather than duplicating the query.
>
> Original plan follows unchanged, for the reasoning behind each fix.

> **Status:** planned, not yet implemented. Triggered by a review of the React frontend added in
> `a7140d8` / `3412535`, which found the Streamlit → React port both incomplete (eight already-computed
> API fields never rendered, all 10 sidebar filters dropped) and numerically wrong in six places that
> are visible on screen. Phase 15 is **frontend + API view-model only** — it does not touch the
> pipeline, the database schema, or `app/dashboard.py`.

### Scope decision: Streamlit is frozen

`app/dashboard.py` is **not modified by this phase**. It stays as a reference implementation and
fallback; React diverges freely from it. Two consequences shape every fix below:

1. **Port, don't extract.** The obvious move for Fix 9 (filters) is to extract the mask logic from
   `_build_sidebar_filters` (`app/dashboard.py:782-812`) into a function both Streamlit and the API
   call. Frozen forbids that, so the API gets its own faithful copy in a new `api/filters.py`. The
   masks are ~20 lines of boolean pandas; a line-by-line port is cheaper than refactoring a file we
   have agreed not to touch, at the cost of a real drift risk that the tests below are written to catch.
2. **New constants live in the API.** `_STALE_BALANCE_DAYS = 3` (`app/dashboard.py:503`) stays at 3
   for Streamlit. `api/viewmodels.py` defines its own `SYNC_STALE_DAYS = 7` / `DORMANT_DAYS = 90`
   and stops importing that constant. The other imports from `app.dashboard` —
   `_enrich_transactions`, `_classify_tx_type`, `_effective_credit_limit`, `_label_subtype` — are
   pure, already covered by `tests/test_dashboard_classify.py` / `tests/test_dashboard_helpers.py`,
   and **continue to be reused as-is**. That reuse is the whole reason `api/viewmodels.py` exists
   (see its module docstring) and Phase 15 does not weaken it.

**Accepted consequence:** after Fixes 1–8, Streamlit and React *deliberately disagree* on every
metric fixed. Streamlit keeps showing a 6000% savings rate and a row-based rolling window. Streamlit
therefore stops being a blanket source of truth; the divergence table under "Verification" below
enumerates exactly which differences are intended, and anything not on that list is a React bug.

### What the audit found

Eight fields the API already computes, and `web/src/lib/types.ts` already types, are **never
rendered by any component**: `credit_utilization`, `forked_accounts`, `income_breakdown`,
`month_over_month` (overview), `weekly_trend`, `monthly_net_by_owner`, `category_distribution`,
`avg_weekly_income`. `useSetCreditLimit()` is defined at `web/src/lib/mutations.ts:18` and has no
caller. Roughly 40% of the port is unbuilt, and almost none of the remaining work needs new backend
computation.

Separately, `api/viewmodels.py:11-17` documents the filter omission as a deliberate R2 scope cut
("these builders take no period/owner/category filter params ... they compute over the full
history"). That cut is the root cause of the "monthly figures look too high" symptom: every number
on the page is an all-time figure.

---

### Fix 1 — savings rate is rendered 100x too large

`api/viewmodels.py:177` and `:303` return **percentage points** (`net_flow / income * 100`).
`web/src/dashboard/OverviewTab.tsx:31` and `CashFlowTab.tsx:89` then apply
`formatPercent = (v) => (v * 100).toFixed(1) + '%'`. A 60% savings rate renders as `6000.0%`.

This is also the whole explanation for the reported "savings rate trend domain of 6000% to -1000%".
`OverviewTab.tsx:119` sets `domain={[0, 1]}`, but Recharts expands a domain to fit data unless
`allowDataOverflow` is set, so real values of `+60` and `-10` produce exactly that axis. The axis is
not broken; it is faithfully rendering doubly-scaled numbers.

The underlying defect is an inconsistent contract: `credit_utilization.pct`
(`api/viewmodels.py:134`) and `budget.pct` (`:406`) are already **fractions**, while `savings_rate`
is percentage points. One `formatPercent` serves both, so one of them is always wrong.

**Fix:** every ratio in the API becomes a fraction. Drop `* 100` at `api/viewmodels.py:177`, `:253`,
`:303`. `formatPercent` is then correct everywhere with no frontend change. Document the unit on
`Overview.savings_rate`, `CashFlowResponse.savings_rate`, and `SavingsRateTrendItem.savings_rate` in
`api/routers/data.py`, and update the test assertions that pin the old percentage-point values.

### Fix 2 — savings-rate trend is nonsense in low-income months

`api/viewmodels.py:253` guards the division with `.clip(lower=0.01)`. A month with $0 income becomes
`(0 - 2400) / 0.01` — **-24,000,000%**. The clip prevents a `ZeroDivisionError` and substitutes
garbage.

**Fix:**
- Return `savings_rate: None` for any month whose income falls below a `$100` floor, and add an
  `income: float` field per point so the frontend can explain the gap rather than silently hiding it.
- Frontend renders nulls as a line break (`connectNulls={false}`) with a footnote naming the skipped
  months ("3 months hidden — no recorded income").
- Clamp the Y domain to `[-1, 1]` with `allowDataOverflow={true}`; mark any month outside it with a
  capped dot whose tooltip carries the true value.
- Restore the **20% target reference line** Streamlit draws (`app/dashboard.py:961-988`) — it is what
  makes the chart readable at a glance.

### Fix 3 — "monthly" income/expenses are inflated and mutually inconsistent

Three independent causes:

**(a) A mislabelled tile.** `OverviewTab.tsx:108` renders `ov.net_flow` under the label **"Net
Monthly Flow"**. `net_flow` is the **all-time** figure (`api/viewmodels.py:176`), sitting between two
genuinely monthly tiles (`avg_monthly_income`, `avg_monthly_expense`). It is larger than its
neighbours by a factor of however many months of history exist. Compute it as
`avg_monthly_income - avg_monthly_expense`.

**(b) No period filter at all.** Fix 9 addresses this at the root.

**(c) Partial months skew the average.** `api/viewmodels.py:181-186` averages over every month
present, including the in-progress current month and a possibly-partial first month, with
`unstack(fill_value=0)` zero-filling gaps. Exclude incomplete months from the "typical month"
average: drop the current calendar month, and drop any boundary month with under 28 days of
coverage. Return `complete_months: int` alongside so the tile can label itself "avg of 3 complete
months" — a number that explains its own window is not a number the user has to trust blindly.

### Fix 4 — owner-balance axis repeats the same two names at random intervals

`api/viewmodels.py:113-122` emits **one row per account**, each labelled with its owner. Recharts is
handed ~12 rows whose `owner` key takes only two distinct values, draws 12 bars, and prints the owner
name under each — hence "Alexie" and "Jacob" recurring at irregular spacing.

Streamlit's equivalent (`app/dashboard.py:579-602`) is a **stacked** bar: `x=owner`,
`y=balance_current`, `color=account_type`, `barmode="relative"`, with a dashed zero line.

**Fix:** aggregate server-side to one row per owner, one column per account type, credit negated so
liabilities sit below the axis:

```python
# {"owner": "Jacob", "depository": 8200.0, "investment": 15400.0, "credit": -1250.0,
#  "net": 22350.0, "accounts": [{"account_name": ..., "type": ..., "value": ...}, ...]}
```

Render as a stacked `BarChart` with `ReferenceLine y={0}` and one `Bar` per account type. The
per-account detail lost to aggregation is recovered in a custom tooltip listing the accounts behind
the hovered segment — on hover, where it is useful, rather than dumped onto the axis, where it is not.

### Fix 5 — the stale-accounts banner is enormous and mislabelled

`_STALE_BALANCE_DAYS = 3` (`app/dashboard.py:503`) flags any account whose balance has not refreshed
in three days. `OverviewTab.tsx:215` then renders each as **"{n} days without activity"** — but
`accounts.updated_at` records the **last balance refresh**, not the last transaction. The label
describes account dormancy while the data measures pipeline health, and at a 3-day threshold nearly
everything qualifies.

The signal is worth keeping rather than deleting: the pipeline runs daily against live production
Plaid tokens, `scripts/plaid_link.py repair` exists precisely because Items break in the real world
(Phase 11), and a silently dead Item is invisible otherwise. What is wrong is the threshold, the
label, and the visual weight.

**Fix — split one conflated warning into two honest signals:**

| Signal | Source | Threshold | Presentation |
|---|---|---|---|
| **Sync health** | `accounts.updated_at` | `SYNC_STALE_DAYS = 7` | Small amber badge on the affected account row in the net-worth section. Tooltip: "Balance last refreshed 9 days ago — the Plaid connection may need repair." No page-wide banner. |
| **Dormant** | `MAX(transaction_date)` per account | `DORMANT_DAYS = 90`, non-zero balance | Collapsed accordion — "3 accounts with no activity in 90+ days" — framed as informational, not a warning. |

The dormant signal needs a computation that does not exist yet: nothing currently derives a
per-account last-transaction date. Add it in `build_net_worth` from the transaction frame `_load()`
already has in hand — no new query, no schema change.

**Deliberately out of scope:** an `accounts.is_archived` column to silence dormant accounts
permanently. It needs a migration, and the tiering above may make it unnecessary. Revisit only if the
dormant list proves to be permanent noise.

### Fix 6 — the Income vs. Expenses chart renders nothing

`CashFlowTab.tsx:165-166` binds `dataKey="INCOME"` and `dataKey="EXPENSE"` — **uppercase**. The API
emits lowercase `income` / `expense` (`api/viewmodels.py:312`, values originating in
`_classify_tx_type`). Both `<Bar>` elements resolve to `undefined` for every row, so the axes, grid,
and legend render and the bars do not.

**Fix:** remove the reshaping rather than correcting the string. Return **wide** rows from the API so
there is no case-sensitive client-side pivot left to get wrong:

```python
# month_over_month: [{"month": "2026-07", "income": 6200.0, "expenses": 4310.0, "net": 1890.0}]
```

This also deletes the hand-rolled `reduce` at `CashFlowTab.tsx:58-69`. Overlay a `net` line on the
grouped bars while we are here — it is the most useful thing this chart can show and comes free from
the new shape.

### Fix 7 — "30-Day Rolling Spend" is labelled "Daily Spend" and is not a 30-day window

Two defects, one cosmetic and one real:

**(a) The label lies.** `CashFlowTab.tsx:196` sets `name="Daily Spend"` on a series that is a 30-day
rolling **total** (`api/viewmodels.py:334`). The reported ~$7,500 is about $250/day over 30 days,
which is plausible — the number is probably right and the label is misdescribing it.

**(b) The window is not 30 days.** `.rolling(30, min_periods=1)` operates on a date-**grouped** frame,
so it counts **30 rows**, not 30 calendar days. Days with no transactions produce no row, so on
sparse data a nominal "30-day" window can silently span two or three months. `min_periods=1`
additionally makes the first 29 points a ramp out of a partial window, which reads as a spending
trend that does not exist.

**Fix:**
- Reindex to a continuous daily `DatetimeIndex`, filling absent days with `0.0`.
- Use a time-based window: `.rolling("30D")`.
- Drop the leading partial window so the series starts at a full 30 days.
- Rename to "Rolling 30-day spend", subtitle "total spent in the 30 days ending on each date", and
  add a companion daily-average series (`rolling_total / 30`) — the number the old label promised.
- Delete `CashFlowTab.tsx:72`'s `.slice(-30)`, which takes the last 30 *points* of a sparse series
  (an arbitrary window); drive the range from the period filter instead.

### Fix 8 — two smaller correctness issues found while tracing the above

- **Sign inconsistency.** `build_cash_flow` returns `expenses` **negative** (`api/viewmodels.py:299`)
  while `build_overview` returns it **positive** (`:175`), so the Cash Flow tab prints a negative
  number in red under "Total Expenses". Normalize both to a positive magnitude and let the UI own the
  sign.
- **Zero renders as "No data".** `OverviewTab.tsx:83` guards with `!data?.net_worth`; a legitimately
  zero net worth is falsy and blanks the entire tab. Use an explicit `== null` check.

---

### Fix 9 — restore all 10 filters, as global URL-synced state

All 10 Streamlit filters (`app/dashboard.py:710-812`) return as **one global filter state** shared by
every tab and synced to the URL, so a filtered view is linkable and survives a refresh.

**Default period: last 3 months** (Streamlit defaults to last 30 days). With a 30-day window every
"average monthly" tile averages exactly one month — the very metric Fix 3 exists to make honest — and
category breakdowns are too thin to read. Three months makes the averages genuinely averages and
gives the Fix 12 baselines something to compare against, with a "This month" preset one click away.

**Server** — new `api/filters.py`, a faithful port (not an extraction; Streamlit is frozen) of the
mask logic at `app/dashboard.py:782-812`, plus a shared query-param dependency consumed by
`/overview`, `/cash-flow`, `/budget`, `/ledger`, `/anomalies`:

```python
class DashboardFilters(BaseModel):
    period: Literal["last_30_days","current_month","last_3_months",
                    "last_6_months","ytd","all_time","custom"] = "last_3_months"
    months: list[str] | None = None      # custom period, ["2026-07", ...]
    owners: list[str] | None = None      # None = all
    categories: list[str] | None = None
    accounts: list[str] | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    search: str | None = None
    outliers_only: bool = False
    duplicates_only: bool = False
```

**Three invariants the port must preserve — all load-bearing, all easy to break silently:**

1. **The two-frame split** (`app/dashboard.py:808-812`). The sidebar returns `filtered` (date +
   non-date masks) *and* `all_time_filtered` (non-date masks only). Trend charts and the
   emergency-fund metric deliberately use the all-time frame so a short period filter does not
   collapse a 12-month trend line to a single point. `build_overview` keeps taking both frames.
2. **Enrich before filtering** (`app/dashboard.py:1357-1361`). Enrichment runs once over the complete
   dataset so internal-transfer pair matching sees both legs of a transfer even when one leg's
   account is filtered out. `prepare_transactions` stays strictly upstream of all filtering.
3. **`duplicates_only` groups on `account_key`, not `account_name`** (`app/dashboard.py:776-792`), so
   two distinct accounts sharing a display name are not collapsed. Likewise the amount range
   tolerates inverted min/max rather than returning zero rows (`:768`).

**Client:**
- `web/src/lib/filters.ts` — filter type, URL serialize/deserialize, defaults.
- `web/src/lib/FilterContext.tsx` — provider syncing to `window.history.replaceState`. No router
  dependency, consistent with the no-router decision recorded at `web/src/dashboard/Dashboard.tsx:19-22`.
- Query keys become filter-aware (`['overview', filters]`). **Required, not optional** — today's keys
  are constants (`web/src/lib/queries.ts:18-23`) and would serve stale data for a new filter set.
- `web/src/dashboard/FilterBar.tsx` — sticky under the tab nav: period preset and owner multi-select
  always visible; the other eight in a "More filters" popover; active non-default filters as
  removable chips with "Clear all"; collapsing to a `Filters (3)` button opening a bottom sheet on
  mobile. Search input debounced 300 ms so typing does not fire a request per keystroke.

### Fix 10 — feature parity with Streamlit

Everything below exists in Streamlit and is missing or degraded in React. Except where noted, the
data is **already in the API response and already typed** — this is rendering work, not backend work.

**Overview tab**

| Feature | Status | Data source |
|---|---|---|
| Assets vs. liabilities by holder (stacked, zero line) | Broken → Fix 4 | `owner_balances` |
| Credit utilisation — per-card bars, `$current / $limit (n% used)`, manual-limit marker | Missing | `credit_utilization` |
| Credit limit editor | Missing | `useSetCreditLimit()` already exists, unused |
| Duplicate-account warning | Missing | `forked_accounts` |
| Income sources donut (top 8 by payee) | Missing | `income_breakdown` |
| Month-over-month by category (grouped bar) | Missing | `month_over_month` |
| Emergency fund — progress toward 6-month goal + caption | Tile only | `emergency_fund_months` |
| Top categories — horizontal, sorted | Vertical, unsorted | `top_categories` |
| `avg_weekly_income` tile | Missing | already returned |

**Cash Flow tab**

| Feature | Status | Data source |
|---|---|---|
| Income vs. expenses by month | Broken → Fix 6 | `month_over_month` |
| Income vs. expenses by week | Missing | `weekly_trend` |
| Monthly net cash flow by holder (grouped, zero line) | Missing | `monthly_net_by_owner` |
| Monthly expense breakdown by category (stacked) | Missing | `category_distribution` |
| 30-day rolling spend | Mislabelled → Fix 7 | `rolling_30d_spend` |
| Caption: transfers excluded from totals | Missing | — |

**Transactions tab** — anomaly scatter (score vs. date, bubble size = amount, colour = category) is
missing entirely; only the table was ported. Ledger explanatory captions (what the Duplicate tick
does, that edits survive pipeline re-runs) are missing. The ledger renders every row unvirtualized.

**Budget tab** — closest to parity. Audit against `app/dashboard.py:1110-1188`, specifically whether
the editor lists **all** categories from `get_categories()` or only those with spend or an existing
limit. Streamlit lists all. Verify-then-fix, not assumed-broken.

### Fix 11 — a design system (there is currently none)

Colours are hardcoded per file: `COLORS` at `OverviewTab.tsx:19`, unrelated inline hexes at
`CashFlowTab.tsx:165-166,193`. Green/red encode income/expense in one place and good/bad in another,
so a large expense and a healthy surplus can render the same colour.

Target look: **bold and data-dense, light + dark**. Derive, via the `dataviz` skill:
- A categorical palette for category series, a sequential ramp for magnitude encoding, and a
  **semantic** positive/negative pair kept strictly disjoint from the categorical palette.
- Direction-aware semantics — expenses up = bad, income up = good, savings rate up = good — encoded
  once in a shared `<DeltaBadge direction polarity>` rather than re-decided per tile.
- Tokens as CSS custom properties in `web/src/index.css`, with `[data-theme]` +
  `prefers-color-scheme`, so **dark mode is a token swap**, not a per-component branch. Both palettes
  contrast-validated; a dense dark dashboard is where weak palettes fail.
- Axis/tooltip/legend/margin specs extracted to `web/src/dashboard/chartTheme.ts`, mirroring what
  `_style_chart()` (`app/dashboard.py:306-324`) does for Plotly.

### Fix 12 — density and context: is this number good?

Every headline metric gains a baseline comparison:

```python
class Metric(BaseModel):
    value: float
    baseline: float | None        # trailing average over complete months
    delta_pct: float | None       # (value - baseline) / baseline
    baseline_months: int          # how many months the baseline averages
    polarity: Literal["normal", "inverse"]   # inverse => up is bad
    sparkline: list[float]        # last 12 months
```

Rendered as `$3,240` plus "up 12% vs your 3-month average" in the polarity-correct colour, with an
inline sparkline in every tile — the cheapest possible "is this normal?" signal, and something
`st.metric` structurally cannot do.

Density additions beyond parity: a **category x month heatmap** (one compact grid replacing several
bar charts, highest information-per-pixel element on the page); a compact KPI grid carrying value +
delta + sparkline instead of a bare number; per-category small-multiple trend lines in the budget
list; and a **committed monthly spend** figure derived from `is_recurring` — a user-set column that
is stored today and surfaced nowhere.

### Fix 13 — hover descriptions for every metric

One registry, `web/src/dashboard/metricInfo.ts`, keyed by metric id:

```ts
{ savingsRate: {
    label: 'Savings Rate',
    definition: 'The share of income you did not spend.',
    formula: '(income - expenses) / income',
    window: 'Selected period',
    excludes: ['Internal transfers between your own accounts',
               'Transactions you flagged as duplicates'] } }
```

A single `<MetricTile>` reads both label and tooltip from this registry, so a label can never drift
from its explanation. The affordance must be **keyboard-focusable and tap-friendly** — a popover, not
a CSS `:hover` title — or it does not exist on mobile, an explicitly supported target (Phase 9).

The `excludes` line does real work: "transfers and duplicate-flagged rows are excluded" answers most
"why doesn't this match my bank?" questions and is currently written nowhere in the UI.

**i18n-ready, English-only for now.** This registry and all other user-facing copy live behind a
single `web/src/lib/strings.ts` from day one. Streamlit keeps its `_STRINGS` en/fr toggle
(`app/dashboard.py:1335`); React ships English, and adding French later is a translation pass rather
than a refactor.

**Drill-down: designed for, deliberately deferred.** `<MetricTile>` takes an optional `onDrillDown`
prop, and each metric id in the registry carries the filter predicate that would produce its
underlying rows. Nothing renders it yet. Adding it later means one side-sheet component and one
filtered-transactions endpoint, with no change to any existing tile.

### Fix 14 — interactivity

- **Cross-filtering** — clicking a category bar anywhere makes it an active filter chip across all
  tabs. The single largest thing React buys over Streamlit's rerun model.
- **Brush/zoom** on the rolling-spend and savings-rate time series.
- **Optimistic ledger edits.** `useUpdateCategory` currently invalidates *every* query
  (`web/src/lib/mutations.ts`), so one category change refetches all six endpoints — each of which
  re-reads and re-enriches the entire transaction table (Fix 15). Apply optimistically to the ledger
  cache and debounce the analytics invalidation.
- **Skeleton loaders** replacing the `Loading cash flow data...` text (`CashFlowTab.tsx:29`).
- **Error states with a next action** — the current error card (`CashFlowTab.tsx:40`) offers no retry.

### Fix 15 — read-path performance (this bites once filters land)

`api/routers/data.py:36-38` — every endpoint calls `_load(db)`, which runs `load_financial_data()` (a
full unbounded `SELECT ... ORDER BY transaction_date DESC`, no LIMIT, `app/dashboard.py:328-347`) and
then re-enriches the whole frame, **per request**. One dashboard load hits five of these; every
ledger edit re-triggers all five.

1. Push the date window into SQL — stop loading all history to render three months. The two-frame
   split means the all-time frame still needs full history, so bound the query to the widest window
   either frame requires, not the narrower one.
2. Add a 60-second TTL cache around `load_financial_data` + `prepare_transactions`, keyed by database
   URL. The data refreshes once daily from the pipeline; a 60-second cache is free correctness.

Considered and **not** adopted initially: collapsing the five endpoints into a single `/dashboard`
call. It trades a real latency win for a coarser cache and a larger invalidation blast radius.

---

### Tests

**Backend** — new cases in `tests/`, existing fixture style:
- Savings rate returns a fraction, not percentage points (Fix 1); the assertions currently pinning
  the old values are updated, not deleted.
- A zero-income month yields `None`, not a clipped extreme (Fix 2).
- `rolling("30D")` over a deliberately sparse series spanning a multi-week gap gives a true
  calendar-day window (Fix 7).
- Owner-balance aggregation collapses N accounts to one row per owner with correct per-type sums and
  credit negation (Fix 4).
- Partial months are excluded from the "typical month" averages (Fix 3c).
- Filter tests (Fix 9): each param narrows results; the all-time frame ignores the date filter;
  transfer pair-matching still classifies both legs when one leg's account is filtered out;
  `duplicates_only` groups on `account_key`; an inverted amount range returns rows rather than none.

**Streamlit's own tests must be untouched and still green** — `tests/test_dashboard_classify.py` and
`tests/test_dashboard_helpers.py` are the check that "frozen" actually held.

Per the standing rule, **none of these may load the real `.env`**: `load_settings()` backfills
production secrets from `.env` even after `os.environ.pop()`. Use isolated env or mocks.

**Frontend** — `web/src/dashboard/*.test.tsx` updated for the new shapes, plus a new assertion that
Income vs. Expenses renders **actual bars**. The current suite passes against a chart displaying
nothing, which is exactly why Fix 6 shipped unnoticed; that gap is the more important thing to close
than the one-line dataKey bug itself.

### Delegation

Model tier chosen per task by the judgment each actually needs, not by size.

- **Opus** — Fixes 1–8 (arithmetic and semantics in shared code, where a plausible-looking wrong fix
  is worse than none); the Fix 9 server-side port (the three invariants above are load-bearing,
  under-documented, and precisely what a cheaper model breaks silently — and the port must be
  faithful to a file we are not allowed to change); the Fix 11 token/palette/polarity system that
  everything downstream applies mechanically; Fix 15 cache keys and invalidation; final review.
- **Sonnet** — Fix 10 parity components (one agent per tab, parallel, built to the spec tables
  above); the Fix 9 client-side filter UI; Fix 12/14 components (`MetricTile`, `DeltaBadge`,
  sparkline, heatmap, cross-filter wiring); component test updates for each.
- **Haiku** — mirroring Pydantic changes into `web/src/lib/types.ts`; transcribing `metricInfo.ts` /
  `strings.ts` from the definition table written in the Opus pass; replacing hardcoded hexes with
  design tokens against a supplied mapping; updating test fixtures for the fraction change; running
  `npm run lint` / `format:check` / `tsc -b` and reporting failures; file-gathering for the Budget
  parity audit.

### Ordering within Phase 15

Fixes 1–8 gate everything: they change the same `api/viewmodels.py` builder signatures Fix 9 then
re-parameterizes, so the two must not run concurrently. Fix 11 (design tokens) can run in parallel
with Fix 9's server half, since they share no files. Fix 10's four tab agents parallelize cleanly
once both land. Fixes 12–14 build on 10 and 11. Fix 15 comes last, when the query shapes have
stopped moving.

**All committing is done by the repo owner.** Work stops at each of six commit points — plan, metric
correctness, filters + design tokens, feature parity, context/tooltips/interactivity, performance +
cleanup — reporting what changed and what was verified, and waits. This phase opens no PR and creates
no branches on its own.

### Verification — expected divergence from Streamlit

Streamlit is frozen, so it remains a valid reference for everything Phase 15 does *not* change: net
worth, assets/liabilities, category totals, budget spend, anomaly lists, ledger contents. Run
`streamlit run streamlit_app.py` beside the React app with matching filters and diff those tab by tab.

The following **must** differ, and each difference is a fix working as intended:

| Metric | Streamlit (frozen) | React (Phase 15) |
|---|---|---|
| Savings rate | percentage points, multiplied by 100 again in the UI | fraction, formatted once |
| Savings-rate trend, zero-income months | plus/minus millions via `clip(0.01)` | `None`, rendered as a gap |
| Rolling 30-day spend | 30-row window | 30-calendar-day window |
| Avg monthly income/expense | includes partial months | complete months only |
| Stale accounts | 3-day balance threshold | 7-day sync + 90-day dormant |

Any divergence **not** on this list is a React bug.

---

## Phase 16 — Dashboard UX pass: dark mode, filters, Home tab, ledger virtualization, drill-down — DONE (2026-08-24)

> **Status (2026-08-24):** All 10 items below are implemented on `dev`, uncommitted at the time of
> writing (the repo owner commits everything themselves). **302 Python tests** green
> (`python -m unittest discover -s tests`) and **242 web tests** green (`npm run test -- --run`).
> `npx tsc -b` produces no output, `npm run lint` is 0 errors / 3 pre-existing warnings (an
> `AuthContext.tsx` fast-refresh warning pair and a `TransactionsTab.tsx` React Compiler
> incompatible-library warning on `useVirtualizer`, both unrelated to this phase's changes), and
> `npm run format:check` is clean. `git diff --stat bf1a53f` (last commit before this session) shows
> 36 files touched, none of them under `app/` — the Streamlit freeze held.

This phase originated from a `/grilling` interview session after direct user feedback on the live
Phase 15 dashboard: dark mode was "horrendous," the filters were "ugly," and — pointing at the wider
goal, not any single screen — the dashboard "needs a lot of love" and should give the user "an idea
about all my money" at a glance rather than requiring a tour through four tabs to answer that.

### Decisions locked (2026-08-24 grilling session)

| # | Decision | Rationale |
|---|---|---|
| 1 | Theme toggle **stays in the header**, three-state (Auto/Light/Dark) | Deviates from an initial recommendation to relocate it; kept per explicit user preference during the interview. |
| 2 | Replace native `<select multiple>` with a **checkbox popover**, not a third-party combobox library | `lib/filters.ts` / `lib/FilterContext.tsx` already hold correct state logic; a popover is a pure presentation swap that reuses it unchanged, versus a library rewrite that would touch state too. |
| 3 | New **Home tab**, set as the default landing tab | The user's complaint was about a first impression, not any one existing tab; a fifth, denser "check-in" surface addresses that without diluting the other four. |
| 4 | Home tab ships **all five** proposed insights, not the recommended two or three | User explicitly asked for "as much data as possible" over a pared-down surface — a deliberate density choice consistent with Phase 15's "don't reduce density" precedent. |
| 5 | Ledger virtualization via **padding-row technique**, not `transform: translateY()` absolute positioning | The translateY approach creates an anonymous table box disconnected from the outer `<table>`'s `<colgroup>`, breaking column-width alignment under `table-layout: fixed`. |
| 6 | Metric drill-down region is `role="button"`, **not a real `<button>`** | `MetricTile` already nests an interactive info-popover `<button>`; a `<button>` cannot validly nest another `<button>`. |
| 7 | Fork-under-merge hardening (item 10) **deferred, not implemented** | Never implicated in any actual reported bug — the TFSA report that raised it turned out to be an unrelated Plaid Link scope issue (item 3). Documented as a known limitation instead of built. |

### Item 1 — Dark mode fix

`Dashboard.tsx`, `SignIn.tsx`, `LoadingScreen.tsx`, and `FilterBar.tsx` were the only files under
`web/src` still using raw Tailwind color utilities (10, 8, 3, and 2 occurrences respectively) against
an otherwise-complete design token system introduced in Phase 15's Fix 11. Every raw color class in
those four files was replaced with the corresponding token, and a ~150ms color-transition was added
so the Auto/Light/Dark toggle doesn't snap. `web/src/test/noRawColors.test.ts` is new: it scans
`web/src` for raw color utility classes and fails the build if one reappears anywhere, closing the
gap that let these four files drift from the token system unnoticed in Phase 15. The header-based
three-state toggle itself is unchanged (see decision 1).

### Item 2 — Filter rebuild

The native `<select multiple>` controls in `FilterBar.tsx` (owners, months, category, account) are
replaced by `web/src/dashboard/MultiSelectPopover.tsx` — a checkbox popover with search and
select-all/clear. The existing `lib/filters.ts` / `lib/FilterContext.tsx` state layer is reused
completely unchanged (decision 2); this was a presentation-only swap.

### Item 3 — TFSA/BNC balance investigation (no code change)

A user report that a TFSA balance was wrong ("$5 vs $5000+ in reality") was investigated by querying
both the `accounts` table and Plaid's `/accounts/get` directly for the affected Item. The originally
suspected cause — a bug in `canonicalize_account_keys` (`database/db.py`) incorrectly
merging/overwriting balances — was **ruled out**: live data showed no such collision. The actual
cause was operational: the user has an investment account at National Bank of Canada (BNC) that was
added to their BNC banking relationship *after* the corresponding Plaid Item was originally linked,
and Plaid only syncs accounts selected at link time (or the most recent Link update-mode session), so
the new account was invisible to that Item — expected Plaid behavior, not data corruption. Fixed
operationally: the user ran `python scripts/plaid_link.py repair --token-suffix fa17bf` (Link update
mode, re-selecting accounts) and confirmed the new account then appeared with the correct balance.

### Item 4 — Savings-rate-trend bug fix

`api/viewmodels.py`'s `savings_rate_trend` computation (originally around lines 471-490) was the only
savings-rate computation in that file that did not apply the `complete_month_keys` filter used
everywhere else (e.g. ~lines 169-180, ~388) to exclude the current, still-in-progress calendar month.
The trend chart's newest point was therefore always a partial month whose ratio swung with every new
transaction — it looked "random" to the user, but was fully deterministic. Fixed by applying the same
filter; a regression test was added asserting the trend excludes the current month, and mutation-
tested (fix removed, test confirmed failing, fix restored, test confirmed passing).

### Item 5 — Balance snapshots

New migration `database/migrations/017_account_balance_snapshots.sql` adds an
`account_balance_snapshots` table. There was previously no balance history at all —
`accounts.balance_current` is overwritten on every pipeline run, so net worth over time was
structurally impossible to compute from stored data before this. `record_balance_snapshots()` and
`get_net_worth_history()` are new in `database/db.py`; `pipeline/runner.py` now calls
`record_balance_snapshots(accounts)` on every run. History starts accumulating the day this shipped —
no backfill was possible.

### Item 6 — Home tab

A new fifth dashboard tab, `web/src/dashboard/HomeTab.tsx`, is now the default landing tab in
`Dashboard.tsx` (decision 3) — a daily check-in surface, with the existing four tabs (Overview, Cash
Flow, Budget, Transactions) unchanged and serving as its "go deeper" drill-down layer. It ships all
five insights the user asked for (decision 4): recurring/committed monthly spend (surfacing the
already-stored but previously-unsurfaced `is_recurring` flag), merchant-level spend breakdown,
month-end cash-flow projection, category drift against the user's own historical baseline, and
subscription detection — plus a net-worth trend line chart once snapshot history (item 5) has
accumulated enough points. Backend: a new `/home` endpoint in `api/routers/data.py` and
`build_home()` in `api/viewmodels.py`. Frontend: `useHome()` in `web/src/lib/queries.ts`, and
`HomeResponse` plus related types in `web/src/lib/types.ts`.

### Item 7 — Visual sharpening pass

Type scale, spacing rhythm, and card/chart treatment were sharpened across `OverviewTab.tsx`,
`CashFlowTab.tsx`, and `BudgetTab.tsx`, driven by concrete, audited class-string mismatches found
across the tabs (card padding, heading scale, a per-state heading bug in `BudgetTab`). Density was
deliberately preserved, not reduced — the user wants the bold, data-dense direction Phase 15 shipped
kept; "sharpened" meant visual craft, not less information.

### Item 8 — Ledger virtualization

`web/src/dashboard/TransactionsTab.tsx` gains `@tanstack/react-virtual` as a new dependency
(`web/package.json`). Ledgers with 50 or fewer transactions still render the original, unchanged
plain `<table>`. Above that threshold, a dual-path render switches to a fixed-height
(`max-h-[70vh]`) scroll container with a sticky header, using a leading/trailing padding-row (spacer
`<tr>`) virtualization technique — chosen over the more common `transform: translateY()` absolute-
positioning approach specifically because of decision 5. `LedgerRow` / `LedgerTheadRow` were
extracted so both the plain and virtualized paths render from identical markup and can't drift apart.
Verified live against the real 592-transaction ledger: only 36 `<tr>` elements were actually mounted
in the DOM at once (`document.querySelectorAll('tbody tr').length` via Chrome DevTools), with smooth
scrolling and a stable sticky header/columns in both light and dark mode.

### Item 9 — Metric drill-down

`MetricTile.tsx` (`web/src/dashboard/`) had an `onDrillDown` prop scaffolded but rendering no UI —
flagged in Phase 15 as "designed for, deliberately deferred." It's now wired: when `onDrillDown` is
passed, the whole tile becomes a `role="button"` region (decision 6), activating on click/Enter/Space,
with `stopPropagation` isolating the nested info-popover button so opening the tooltip never also
triggers the drill-down. New `web/src/dashboard/tabs.ts` holds a shared `TabId` type, avoiding an
import cycle between `Dashboard.tsx` and `HomeTab.tsx`. `Dashboard.tsx` now passes
`onNavigate={setActiveTab}` into `HomeTab`, which wires it to its three status-row tiles: **Net
Worth → Overview tab**, **Committed Monthly Spend → Transactions tab**, **Projected Month-End
Spend → Budget tab** — each landing on the existing tab with the fuller picture for that metric.
Live-verified in Chrome: all three tiles correctly switch tabs on click; clicking a tile's "?" info
badge opens its tooltip and does not trigger navigation.

### Item 10 — Deferred by explicit decision: fork-banner under-merge hardening

The existing account-fork warning banner (`_section_net_worth` in `app/dashboard.py:538-543`,
mirrored via the `_IDENTITY_COLS` fork-size check in `api/viewmodels.py:255-260`) groups `accounts`
rows by identity `(official_name, account_subtype, account_type, mask)` and flags any group where
**more than one** `account_key` row shares that identity — an over-fork, the same real Account
represented twice. It is structurally unable to detect the opposite failure: two genuinely different
Accounts collapsing onto **one** `account_key` row (an under-merge), because an under-merge, by
definition, destroys the very multi-row signal the check looks for — there is nothing left to count.

Hardening this was discussed during the grilling session and explicitly **not implemented**
(decision 7): it was never implicated in any actual reported bug (the TFSA report that prompted the
discussion turned out to be the BNC Plaid-Link scope issue in item 3, unrelated to account-identity
merging at all), so per the user's decision it is left as a documented, known limitation rather than
built speculatively. See `docs/adr/0001-heuristic-account-identity.md`, whose Consequences section
now cross-references this phase.

### Verification

- Python: `python -m unittest discover -s tests` — 302 tests, all passing.
- Web: `npm run test -- --run` — 242 tests across 18 files, all passing.
- `npx tsc -b` — clean, no output.
- `npm run lint` — 0 errors, 3 pre-existing warnings (unrelated to this phase; see status block above).
- `npm run format:check` — clean.
- `git diff --stat bf1a53f` — 36 files changed, all under `web/`, `api/`, `database/`, `pipeline/`,
  and `tests/`; `app/` untouched, confirming the Streamlit freeze held.
- Manual, live-browser verification (Chrome DevTools, signed-in session): ledger virtualization DOM
  node count (item 8) and drill-down navigation + tooltip isolation (item 9), both described above.

---

## Phase 17 — Migrate Plaid ingestion to `/transactions/sync` — IMPLEMENTED (2026-08-25), test coverage pending

A hotel stay at Le Germain produced **five stored rows** where the bank shows **one charge**. The user
booked the room, put down a deposit to secure the stay, and ate at the restaurant; the card issuer
authorized each separately and then settled everything as a single `-723.01` charge. Four of the five
stored rows sum to ~724 — close to the settled total but not equal, which is the normal signature of
released holds and tip adjustments rather than a clean partition.

**Root cause:** `ingestion/plaid_ingestor.py` uses `/transactions/get`, fetching and immediately
discarding both `pending` and `pending_transaction_id`. In Plaid's model a pending authorization that
posts becomes a **brand-new transaction with a new `transaction_id`**, and the pending one simply **stops
appearing** in `/transactions/get`. There is no removal signal. `build_transaction_hash` keys on
`transaction_id`, so the settled `-723.01` lands as a new row while the four superseded authorizations
persist forever. `reconcile_transactions` cannot close this: it buckets by natural key `(account_key,
transaction_date, description, amount)`; each stale authorization has a distinct amount, so Plaid
returns **zero** of that key and the guard deliberately skips it. That guard protects real history aging
out of Plaid's rolling window and is correct — it is simply blind to this case.

**Intended outcome:** Move to `/transactions/sync`, whose `removed` array reports superseded and
reversed transactions explicitly. Pending→posted stops being inference. Going forward a stay like this
settles into one row without user intervention.

### Decisions locked

| Question | Decision |
|---|---|
| Verify before building | **Yes** — read-only probe against live Plaid first |
| Delete or flag superseded rows | **Delete** on exact Plaid lineage (`removed`); flag only on heuristic |
| The 4 stale Germain rows already stored | **Manual** — user flags them with the existing `is_duplicate` checkbox |
| Scope | Migrate to `/transactions/sync` |
| `reconcile_transactions` | **Keep, but run only on a full-refresh sync** |
| Initial-sync history depth | **Accept full history** (not capped to 90 days) |
| `BaseIngestor` seam | **Keep `fetch_transactions`**; add a parallel `sync_transactions()` |
| Old `/transactions/get` path | Keep as rollback insurance; delete in a follow-up |
| Store Plaid's `pending` flag | **Yes**, ingest and store; do not surface in the UI yet |

### The hazard this phase must close

`reconcile_transactions` assumes the fetched frame is *everything Plaid currently returns for the
window*. Under `/transactions/sync`, after the first run the frame is only the delta. The zero-count
guard protects untouched keys, but a key present in the delta is **not** protected: the user really
made four separate `IKEA $250.00` charges on 2026-07-02. If Plaid `modified` one of them, the delta
carries **one** row for that natural key, the DB holds **four**, `excess = 3`, and the reconciliation
logic deletes **three genuine transactions**. Therefore reconcile must be **structurally** prevented from
running on a delta — gated by a `full_refresh` flag threaded from the ingestor, not by convention or
comment.

### Probe result (2026-08-25, all 3 production institutions): Gate passed

Sync returned 200 on all 3 tokens (204/331/187 transactions, history back to March–April 2026). A Le
Germain match was found: exactly one live row (the settled `$723.01` charge, `pending=False`,
`pending_transaction_id=bNvnqEP3...Ee13EE`), and the DB holds 5 Germain rows with the same
`pending_transaction_id` matching stored `external_id` on one of them (`id=18969`, `$524.81`) exactly.
The other three stored rows (`$0.00`, `$198.20`, `$1.39`) have no lineage evidence in the current
snapshot — expected, since a cold-start sync (`cursor=null`) has no prior baseline for `removed` to
reference; they remain the manual cleanup case. **The union rule is confirmed:** this first sync
`removed` was empty, but `pending_transaction_id` on the settled row carries the lineage pointer,
so the effective deletion signal must be the union of Plaid's explicit `removed` array **and** every
non-null `pending_transaction_id` on `added`/`modified` rows.

### Shipped contracts

**`SyncResult` dataclass** (`ingestion/plaid_ingestor.py`):
```python
@dataclass
class SyncResult:
    added: pd.DataFrame                    # same normalized columns as IngestResult produces
    modified: pd.DataFrame                 # same shape
    removed_ids: list[str]                 # Plaid transaction_ids — union of removed[] + pending lineage
    duplicate_accounts_skipped: int
    full_refresh: bool                     # True iff EVERY token started from a null cursor
    cursors: dict[str, str]                # token_fingerprint (sha256) -> next_cursor
```

**Ingestor method:** `sync_transactions(self, stored_cursors: dict[str, str]) -> SyncResult` — fetches
all deltas since the last sync. `stored_cursors` is keyed by `token_fingerprint = sha256(access_token).hexdigest()`;
the raw token is never stored or logged, only its fingerprint.

**DB methods:**
- `get_sync_cursors() -> dict[str, str]` — returns `{token_fingerprint: cursor}` for every Item with a prior sync
- `set_sync_cursor(fingerprint, cursor)` — persists the next cursor for one Item. Must only be called after every
  write (upsert, delete, reconcile) has committed — advancing the cursor first means a crash mid-write loses
  that delta permanently.
- `delete_transactions_by_external_ids(external_ids: list[str]) -> int` — deletes rows by Plaid's authoritative
  `removed` lineage. Safe to call on a delta. Returns the number of rows deleted.
- `reconcile_transactions(..., *, full_refresh: bool)` — now requires keyword-only `full_refresh: bool`, raises
  `ValueError` if False. Reconciliation is only sound when the fetched frame is the full current window, not a
  delta; the guard prevents the IKEA-delta hazard.

**Migrations:**
- `018_plaid_sync_state.sql`: Creates `plaid_sync_state` table with `token_fingerprint` (TEXT PRIMARY KEY),
  `cursor` (TEXT NOT NULL), `updated_at` (TIMESTAMPTZ DEFAULT NOW())
- `019_transaction_pending.sql`: Adds `pending` (BOOLEAN, nullable on purpose) and `pending_transaction_id` (TEXT)
  columns to `transactions`. NULL means "ingested before this phase, status unknown" and must never be confused with FALSE.
- `020_pipeline_runs_sync.sql`: Adds `removed_count` (INTEGER) and `full_refresh` (BOOLEAN) columns to `pipeline_runs`

**Pipeline orchestration** (`pipeline/runner.py::run_pipeline`):
1. `sync_transactions()` — fetch added/modified/removed
2. Canonicalize account keys, upsert accounts, snapshot balances
3. Classify + score `added ∪ modified`
4. `upsert_transactions(added ∪ modified)`
5. `delete_transactions_by_external_ids(removed_ids)`
6. `reconcile_transactions(..., full_refresh=True)` **only if** `result.full_refresh`
7. `set_sync_cursor()` for each token — **last**, after every write above has committed

Step 7's position is load-bearing: advancing the cursor before rows are durable means sync never
replays that delta and those transactions are lost permanently.

### Verification

- All existing Python tests green (`python -m unittest discover -s tests -v`).
- Initial sync with a null cursor sets `full_refresh=True`; a second run with a stored cursor sets it `False`.
- A `removed` id deletes exactly that row and nothing else.
- **The IKEA regression test:** four stored `IKEA $250.00` rows on one date; a delta modifying one of them;
  assert `reconcile_transactions` is not called and all four rows survive.
- `reconcile_transactions(full_refresh=False)` raises `ValueError`.
- Cursor is not persisted when the upsert raises.
- `pending` / `pending_transaction_id` round-trip through sync runs; `user_category` / `is_recurring` / `is_duplicate`
  survive and are unmodified.
- `token_fingerprint` is a sha256 hex digest, never the raw token.

### Follow-ups (not in this phase)

1. Delete the old `fetch_transactions`/`/transactions/get` path once sync has run clean in production
   for approximately 2 weeks, confirming cursor state is stable and no crashes are eating deltas.
2. Decide whether to surface `pending` in the ledger UI — currently stored but unsurfaced.

### References

See `docs/adr/0003-transactions-sync-and-superseded-authorizations.md` for the detailed rationale behind
this phase (the Germain case as motivating example, why `/transactions/get` structurally cannot solve it,
why reconcile is kept but gated, and why `removed` justifies deletion where `is_duplicate` justifies
only flagging).

---

## Appendix A — Potential adjustments: dashboard interactivity (future, non-blocking)

> Not on the publish-critical path. These extend the dashboard from "read + light edit" toward a working
> notebook the two users can annotate and correct. Every item follows the **"pipeline never writes it"**
> rule (like `user_category`), so edits survive `upsert_transactions`. Schedule after Phases 1–6 land;
> several pair naturally with Phase 7 (the confirm/review workflow *produces* labeled training data).

**Shared foundation (one migration + mirrored DB methods).** A single idempotent migration
`database/migrations/004_interactivity.sql`, picked up automatically by `ensure_schema()` (3d):

```sql
-- Manual annotations + review flags. Pipeline never writes these columns.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_note        TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_status  TEXT;    -- NULL | 'confirmed' | 'review'
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS outlier_reviewed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE budgets      ADD COLUMN IF NOT EXISTS note             TEXT;
```

New `DatabaseClient` methods (mirror `update_transaction_category` in 3b — same single-`UPDATE`,
`updated_at = NOW()` shape; all parameterized):
- `update_transaction_note(transaction_hash, note)` — writes `transactions.user_note`.
- `set_category_status(transaction_hash, status)` — writes `transactions.category_status`.
- `set_outlier_reviewed(transaction_hash, reviewed)` — writes `transactions.outlier_reviewed`.
- Extend `upsert_budget(category, monthly_limit, note=None)` to carry the note (keep the signature
  backward-compatible with 3k).
- `get_budgets` / the ledger SELECT (3e) must also select the new columns
  (`COALESCE`-free — they're read as-is): add `user_note`, `category_status`, `outlier_reviewed` to
  the `tx_query`, and `note` to `get_budgets`.

Dashboard wiring reuses the existing `st.data_editor` + `edited_rows` change-detection (3l) so only
cells the user actually changed trigger a DB write — no new pattern to invent.

### A1. Budget notes / comments
- Add an editable **Note** column to the 3k budget editor (`st.column_config.TextColumn`).
- On save, pass the note through the extended `upsert_budget`.
- Render each category's note as an `st.caption` under its budget progress bar.
- *Why useful:* records the intent behind a limit ("summer travel fund", "cut after Q3") so the number
  isn't context-free next month.

### A2. Transaction notes
- Add an editable **Note** column to the 3l ledger editor, persisted via `update_transaction_note`.
- *Why useful:* "reimbursable", "gift for Sam", "one-off" — the context that makes a line item legible
  weeks later, and the raw material for later exclude/split rules (A5/A9).

### A3. Category confirm / review  (pairs with Phase 7)
- Add a **Status** `SelectboxColumn` to the ledger: blank / `confirmed` / `review`, via `set_category_status`.
- Surface a "Needs review" filter/count on the Transactions tab (`category_status = 'review'` or NULL on
  placeholder-categorized rows).
- *Why useful now:* a human-in-the-loop correctness signal. *Why useful for Phase 7:* every `confirmed`
  row (description + effective category) is a **labeled training example** — extend the deferred
  `seed_sample_data.py --labeled` export path to also dump confirmed real transactions, closing the
  active-learning loop (classify → user confirms/corrects → retrain).

### A4. Anomaly review / dismiss
- In `_section_anomalies` (Transactions tab), add a **Reviewed** checkbox column, persisted via
  `set_outlier_reviewed`; default the anomaly view to hide reviewed rows (with a "show all" toggle).
- *Why useful:* the 3 seeded outliers (and real ones once ML is on) can be acknowledged so the section
  reflects *open* items, not a static list.

### Further ideas (lighter — capture, don't spec yet)
- **A5. Exclude from analytics** — `transactions.excluded BOOLEAN` to drop reimbursements / mis-imports
  from budgets and cash-flow without deleting the row.
- **A6. Merchant → category rules** — a small `category_rules(pattern, category)` table applied
  post-classification; "always map `Tim Hortons` → Dining". High leverage; also feeds Phase 7.
- **A7. Savings goals** — a `goals` table (name, target, deadline) with an Overview progress tile.
- **A8. Category management UI** — add / rename / merge categories from the app (extends the existing
  `categories` table + `get_categories`).
- **A9. Split transaction** — allocate one transaction across multiple categories (child-rows table).
- **A10. Recurring / subscription tagging** — flag recurring charges; forecast upcoming bills.

### Cross-cutting for any item above
- New `_STRINGS` keys in **both** `en` and `fr` (follow the 3h pattern).
- Tests (Phase 6 style, pure/mocked): extend `test_db_upserts.py` for each new DB method (assert SQL
  targets the correct `user_*` / flag column, params in order); extend `test_dashboard_helpers.py` if any
  pure helper is added. No live DB / network.
- Ordering: land the shared migration + DB methods before wiring any tab; keep the pipeline oblivious to
  every new column (verify `runner.py` / `upsert_transactions` never reference them).

---

## Ordering constraints / risks

1. Phase 2a (CSV removal, incl. config/runner refactor) **before** 2b (seed script) — the seed script relies on `load_settings()` succeeding with only `DATABASE_URL` set.
2. Phase 3c migrations (budgets, user_category, category seed) should land **before** demoing the seed data — the seed categories match the 3c canonical list, and `ensure_schema` (3d) must pick up all migration files. The seed script itself only needs 001, but run it after 3c/3d to avoid a re-seed.
3. Phase 3a (`_classify_tx_type` fix) **before** all other Phase 3 sections.
4. Phase 3b (DB methods) **before** Phases 3k and 3l.
5. Phase 3c (migrations) **before** Phase 3d (`ensure_schema` iteration) — 3d relies on the files existing.
6. Phase 3e (SELECT query with COALESCE + `transaction_hash`) **before** Phase 3l (ledger edit).
7. Fix case in `analytics/placeholders.py` (`"uncategorized"` → `"Uncategorized"`) **alongside** Phase 3c, before running the pipeline against the seeded categories.
8. **Don't change `build_transaction_hash` inputs without a rehash + dedup migration** — re-ingest
   idempotency depends on them. Superseded three times, each deliberately and each shipped together with
   `rehash_transactions()`: Phase 2.7 (2026-07-17, `account_name`-keyed → `account_key`-keyed), Phase 2.8
   (2026-07-19, amount/date canonicalisation), and Phase 12b (2026-07-27, → Plaid's `transaction_id` when
   present, with the `account_key`-keyed formula retained only as the fallback for rows without one).
   Note 12b also makes the hash *account-independent* for Plaid rows, which is what lets a re-attributed or
   pending→posted-revised transaction update in place instead of inserting a twin.
9. Seed data must use Plaid sign convention (positive = outflow) or cash flow inverts.
10. `load_settings()` must never hard-require Plaid credentials — that would break the seed demo and dashboard-only deployments. Plaid validation lives only in `pipeline/runner.py::_build_ingestor`.
11. Cron goes live only after merge to `main` + GitHub Secrets — Phase 0 owner action, not code.
12. Phase 2.5 (security hardening) lands **after** Phase 2 (it edits the refactored `config.py`/`runner.py`)
    and **before** the `dev → main` publish merge — it is a publish blocker, together with Phase 5 and 1f.
13. 2.5a (`enforce_tls`) must land before any production `DATABASE_URL` is pointed at Supabase/Neon.
14. The pending-state dict stays module-level (2.5d) — do NOT move it into `st.session_state`; session
    state does not survive the OAuth redirect and the flow would break on every sign-in.
15. Phase 3o (quick-range period filter) lands after 3g/3i/3j and before 3n — it changes
    `_build_sidebar_filters`'s return shape and adds the `all_time_df` parameter to `_section_overview`.
16. Phase 3p (weekly metrics) lands after 3o, since it builds on the same `_section_overview` /
    `_section_cash_flow` signatures 3o just changed, and before 3n — it adds to the Overview and Cash-flow
    sections those tabs already assemble; it does not touch Budget (3k), which stays monthly-only.
17. Phase 3q (`is_recurring` tagging) is planning-only for now — not implemented alongside 3o/3p. If picked
    up later, its migration lands after 3c/3p's migrations, and its ledger checkbox reuses the 3l
    edited-rows pattern; it must not be conflated with ML-based recurrence detection, which is out of scope.
18. Phase 9 (mobile) lands **after** Phase 3 — it restyles the very sections 3i/3j/3k/3l assemble, so doing it
    earlier means restyling twice. It is **not** a publish blocker. Internally, 9a (the CSS mechanism) must
    land before 9b/9e/9f, which all write rules into `app/static/mobile.css`.
19. Phase 10a (root `streamlit_app.py`) is a **hard prerequisite** for any deploy to Streamlit Community
    Cloud — without it the app cannot import `core` on a host that has no editable install. It is
    independent of Phases 6/8/9 and can land at any time.
20. Phase 10's deploy sequence is order-locked by a chicken-and-egg: the app URL does not exist until the
    first deploy, so the Google redirect URI cannot be registered before it. Deploy → read URL → register in
    the Google console → set `GOOGLE_OAUTH_REDIRECT_URI` → reboot. Expect the first boot's sign-in to fail.
21. Phase 10 requires the `dev → main` merge first (10e) — SCC should track a stable branch, and the same
    merge is what activates the Actions cron (constraint 11). One merge satisfies both.
22. Phase 9 (mobile) is best done **before** Phase 10's deploy is shared around, since mobile sign-in is the
    main reason the public HTTPS URL exists — but it is not a technical blocker, and 10 can ship first.
23. Phase 15 freezes `app/dashboard.py`. Nothing in Phase 15 may edit it, and
    `tests/test_dashboard_classify.py` / `tests/test_dashboard_helpers.py` must stay untouched and green —
    that pair is the check that the freeze held. The API keeps *reusing* that module's pure helpers
    (`_enrich_transactions`, `_classify_tx_type`, `_effective_credit_limit`, `_label_subtype`); the freeze
    forbids modifying it, not importing from it. The one import Phase 15 drops is `_STALE_BALANCE_DAYS`,
    which the API replaces with its own `SYNC_STALE_DAYS` / `DORMANT_DAYS`.
24. Appendix A's interactivity items were written against Streamlit's `st.data_editor`. With Streamlit
    frozen as of Phase 15, any of them that get built should target the React dashboard instead, reusing
    the existing write endpoints in `api/routers/data.py` rather than adding Streamlit widgets. The
    "pipeline never writes it" rule they depend on is unaffected.

---

## Verification

1. `python -m unittest discover -s tests -v` — all green on Python 3.12 and 3.13.
2. `docker compose up -d && python scripts/seed_sample_data.py` — no errors; rows in DB with owners, categories, and 3 outlier flags. **No Plaid env vars set** — proves the zero-credential demo path.
3. Run `python scripts/seed_sample_data.py` a second time (same day) — row count unchanged (idempotency via `transaction_hash`).
4. `python main.py` with no Plaid creds → fails fast with a clear `ConfigError` naming the missing Plaid vars (pipeline-level enforcement, not a stack trace from deep inside PlaidIngestor).
5. `streamlit run app/streamlit_app.py` — sign in with Google; all 4 tabs render; Overview/Net worth/Cash flow/Budget sections populate with categorized data; Transactions tab shows ledger with category dropdown populated from DB canonical list; category edit persists on page refresh; anomaly section shows the 3 seeded outliers.
6. Filter the sidebar to a past month → Budget tab shows that month's spending; "Projected EOM" is replaced by "Actual".
7. `pip install -e .` in a fresh venv → same deps as `pip install -r requirements.txt`.
8. Push branch → CI runs green on 3.12 + 3.13.
9. `git grep -iE "csv_paths|ingestion_source|csv_ingestor"` → no matches outside PLAN.md (CSV fully removed).
10. `git grep -E "jacos|jacosse|lapointe|gmail\.com|C:\\\\Users"` → no matches.
11. TLS enforcement: `python -c "from core.config import enforce_tls; print(enforce_tls('postgresql://u:p@db.example.com/x'))"` → ends with `sslmode=require`; same call with `localhost` → unchanged.
12. Sign in with a Google account **not** on `GOOGLE_ALLOWED_EMAILS` → rejected with the generic "not allowed" message.
13. Stop the database, load the dashboard → browser shows the generic "check the server logs" error; no host/user/DSN fragment anywhere in the page.
14. `pip install --require-hashes -r requirements.lock` succeeds in a fresh venv; `pip install -r requirements.txt` still works for loose installs.
15. From a mobile browser, sign in via the HTTPS redirect URI with both allowlisted accounts → dashboard renders.
16. `docker compose up -d` → `docker port <postgres-container>` shows `127.0.0.1:5433` (loopback only), and the seed + dashboard flow still works locally.
17. Both workflow files: every `uses:` is a full 40-char commit SHA; the daily job has `timeout-minutes` and a `concurrency` group.
18. `ruff check . && ruff format --check .` pass on the branch; the CI lint job (Phase 8a) is green.
19. (When Appendix A items are built) each new user-edit column is pipeline-immune: edit a note/status/reviewed flag, then run `python main.py` (or re-`upsert` the same rows) → the edit is retained.
20. (When Phase 9 is built) the dashboard renders with no horizontal page scroll at 390px, 360px, and 768px
    viewport widths, in **both** `en` and `fr`, across all four tabs.
21. (When Phase 15 is built) `cd web && npm run test && npm run build && npm run lint` all pass; the React
    dashboard renders bars in Income vs. Expenses, a savings-rate axis inside plus/minus 100%, exactly one
    x-axis label per account holder, and a reachable keyboard-only tooltip on every KPI tile. Diffing it
    against `streamlit run streamlit_app.py` at matching filters shows **only** the five intended
    divergences tabulated at the end of Phase 15.
