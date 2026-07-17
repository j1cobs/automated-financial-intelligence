# Publish-Readiness + Dashboard Expansion Plan

> Working plan to make this repo publishable on GitHub (interview showcase + self-host template) **and** expand the dashboard with meaningful financial insights.
> Status: **not started** — tick checkboxes as work lands. Safe to delete once all phases complete.
> Implement phases in order. Phase 3 (dashboard) is the largest; it has strict internal ordering.
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

## Phase 0 — Owner actions (no code; checklist)

The local untracked `.env` holds **live production credentials**. Git history is verified clean but rotate as a precaution:

- [ ] Rotate Supabase DB password; update local `.env` + GitHub Secrets.
- [ ] Rotate Plaid production secret; re-issue all three access tokens.
- [ ] Rotate (or recreate) the Google OAuth client secret.
- [ ] Set the production Google OAuth redirect URI to the **HTTPS** public dashboard URL (mobile sign-in
  depends on it); keep `http://localhost:8501/` only as a second, dev-only redirect in the Google console.
- [ ] Confirm `GOOGLE_ALLOWED_EMAILS` in production secrets lists exactly the two authorized addresses.
- [ ] Confirm the managed Postgres (Supabase/Neon) tier has encryption at rest enabled (both do by default — verify).
- [ ] At publish time: merge `dev` → `main`, populate GitHub Secrets (cron only runs from the default branch).
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
requires-python = ">=3.11"
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
- **Lines 72-75** (Automation section): replace "still on the dev branch and uncommitted" with "committed but inert until required Secrets are populated on the default branch."
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

**Fix**: render the link inside a real (unsanitized) HTML snippet via
`streamlit.components.v1.html`, using `<a href="..." target="_top">`. `target="_top"` tells the browser to
navigate the *top-level browsing context* (the actual tab), not the sandboxed iframe hosting the component —
so the whole tab navigates to Google and back, with no second tab ever opening.

### File: `app/auth.py`

1. Add imports: `html` (stdlib, for escaping the URL into an attribute) and
   `streamlit.components.v1 as components`.
2. Replace line 134:
   ```python
   st.markdown(f"[Continue with Google]({auth_url})")
   ```
   with:
   ```python
   safe_url = html.escape(auth_url)
   components.html(
       f'''
       <a href="{safe_url}" target="_top"
          style="display:inline-block;padding:0.5em 1em;background:#4285F4;color:white;
                 border-radius:4px;text-decoration:none;font-family:sans-serif;">
           Continue with Google
       </a>
       ''',
       height=50,
   )
   ```
   Keep the existing `st.caption(...)` line below it as-is.

No changes needed to `core/google_oauth.py` or `consume_google_callback` — the redirect URI and query-param
handling are unaffected; only how the *outbound* link is rendered changes.

### Verification
- `streamlit run app/streamlit_app.py`, load the sign-in page, confirm the "Continue with Google" button
  renders correctly (styling/height, no scrollbar clipping from the iframe).
- Click it and confirm the browser navigates *within the same tab* to Google's consent screen (no new tab),
  and after granting consent, Google redirects back to the same tab and the dashboard loads signed in.
- Sign out and sign in again to confirm the flow is stable on repeat.

---

## Phase 3 — Dashboard improvements

Implement the steps in the lettered order below. They build on each other. Do not skip ahead.

### 3a. Fix `_classify_tx_type` in `app/dashboard.py`

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

### 3q. Recurring-transaction tagging — user-taggable `is_recurring` column

**PLANNING ONLY — do not implement.** Captures the shape of the feature so a later phase can build it
without re-deriving the design. No code, migration, or UI change lands as part of writing this section.

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

## Phase 4 — Docs

### 4a. Rewrite `README.md`

Structure (link to `docs/` for depth; keep each section skimmable):

```markdown
# automated-financial-intelligence

> Modular personal-finance platform: ingest bank transactions → classify with ML →
> persist in PostgreSQL → explore in a secure Streamlit dashboard. Built for self-hosting.

[CI badge] [License badge] [Python 3.11+ badge]

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
Python 3.11+ required. Run all commands from repo root. Plaid credentials are only needed to ingest real data via `python main.py`.

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
      matrix:
        python-version: ["3.11", "3.12"]
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
by a review checklist **and** automated tooling in CI.

### 8a. Tooling — ruff + black

- Dev-only tools (NOT added to `requirements.txt`; document in `CONTRIBUTING.md`, Phase 4f). Install:
  `pip install ruff black`.
- Add config to `pyproject.toml` (extends the 1c rewrite):
  ```toml
  [tool.black]
  line-length = 110
  target-version = ["py311"]

  [tool.ruff]
  line-length = 110
  target-version = "py311"
  extend-exclude = ["venv_automated_financial_intelligence"]

  [tool.ruff.lint]
  select = ["E", "F", "I", "UP", "B"]   # pyflakes, pycodestyle, isort, pyupgrade, bugbear
  ```
  (Confirm `line-length` against the current code before committing — pick the value that reformats least;
  110 is a starting proposal, adjust to the repo's actual longest-common width.)
- Add a **lint job** to `.github/workflows/ci.yml` (Phase 5a), parallel to the test job:
  ```yaml
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<full-commit-SHA>      # SHA-pinned, per Phase 5 security note
      - uses: actions/setup-python@<full-commit-SHA>
        with: { python-version: "3.12" }
      - run: pip install ruff black                    # dev tools; not hash-locked runtime deps
      - run: ruff check .
      - run: black --check .
  ```
  Actions stay SHA-pinned (Phase 5). Keep this non-blocking-optional at first if a full reformat is noisy;
  make it required once the tree is clean.

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
- `ruff check .` and `black --check .` pass locally and in CI.
- `python -m unittest discover -s tests -v` still green (formatting changed nothing behavioral).
- `git grep -E "jacos|jacosse|gmail\.com|C:\\\\Users"` → no matches (reaffirm the Phase-level rule).

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
8. **Never** change `build_transaction_hash` inputs — re-ingest idempotency depends on them.
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

---

## Verification

1. `python -m unittest discover -s tests -v` — all green on Python 3.11 and 3.12.
2. `docker compose up -d && python scripts/seed_sample_data.py` — no errors; rows in DB with owners, categories, and 3 outlier flags. **No Plaid env vars set** — proves the zero-credential demo path.
3. Run `python scripts/seed_sample_data.py` a second time (same day) — row count unchanged (idempotency via `transaction_hash`).
4. `python main.py` with no Plaid creds → fails fast with a clear `ConfigError` naming the missing Plaid vars (pipeline-level enforcement, not a stack trace from deep inside PlaidIngestor).
5. `streamlit run app/streamlit_app.py` — sign in with Google; all 4 tabs render; Overview/Net worth/Cash flow/Budget sections populate with categorized data; Transactions tab shows ledger with category dropdown populated from DB canonical list; category edit persists on page refresh; anomaly section shows the 3 seeded outliers.
6. Filter the sidebar to a past month → Budget tab shows that month's spending; "Projected EOM" is replaced by "Actual".
7. `pip install -e .` in a fresh venv → same deps as `pip install -r requirements.txt`.
8. Push branch → CI runs green on 3.11 + 3.12.
9. `git grep -iE "csv_paths|ingestion_source|csv_ingestor"` → no matches outside PLAN.md (CSV fully removed).
10. `git grep -E "jacos|jacosse|lapointe|gmail\.com|C:\\\\Users"` → no matches.
11. TLS enforcement: `python -c "from core.config import enforce_tls; print(enforce_tls('postgresql://u:p@db.example.com/x'))"` → ends with `sslmode=require`; same call with `localhost` → unchanged.
12. Sign in with a Google account **not** on `GOOGLE_ALLOWED_EMAILS` → rejected with the generic "not allowed" message.
13. Stop the database, load the dashboard → browser shows the generic "check the server logs" error; no host/user/DSN fragment anywhere in the page.
14. `pip install --require-hashes -r requirements.lock` succeeds in a fresh venv; `pip install -r requirements.txt` still works for loose installs.
15. From a mobile browser, sign in via the HTTPS redirect URI with both allowlisted accounts → dashboard renders.
16. `docker compose up -d` → `docker port <postgres-container>` shows `127.0.0.1:5433` (loopback only), and the seed + dashboard flow still works locally.
17. Both workflow files: every `uses:` is a full 40-char commit SHA; the daily job has `timeout-minutes` and a `concurrency` group.
18. `ruff check . && black --check .` pass on the branch; the CI lint job (Phase 8a) is green.
19. (When Appendix A items are built) each new user-edit column is pipeline-immune: edit a note/status/reviewed flag, then run `python main.py` (or re-`upsert` the same rows) → the edit is retained.
