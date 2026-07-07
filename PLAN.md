# Publish-Readiness + Dashboard Expansion Plan

> Working plan to make this repo publishable on GitHub (interview showcase + self-host template) **and** expand the dashboard with meaningful financial insights.
> Status: **not started** — tick checkboxes as work lands. Safe to delete once all phases complete.
> Implement phases in order. Phase 3 (dashboard) is the largest; it has strict internal ordering.

---

## Phase 0 — Owner actions (no code; checklist)

The local untracked `.env` holds **live production credentials**. Git history is verified clean but rotate as a precaution:

- [ ] Rotate Supabase DB password; update local `.env` + GitHub Secrets.
- [ ] Rotate Plaid production secret; re-issue all three access tokens.
- [ ] Rotate (or recreate) the Google OAuth client secret.
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
Rationale: `artifacts/` is the default `MODEL_PATH` dir; `data/` is where real bank CSVs and generated sample data live; ignoring the whole `data/` directory is safe because sample data is produced by a committed *generator* script (Phase 2b).

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

**Change** the demo defaults so the file works out-of-the-box with docker (Phase 2c):
```env
DATABASE_URL=postgresql://finance:finance@localhost:5432/finance
CSV_PATHS=data/sample/transactions.csv
```

**Add** these missing optional vars (both read by `core/config.py:119-120`):
```env
# SUPABASE_URL=https://yourproject.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=...
```

**Final group structure** for clarity:
```
# ── Required ────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://finance:finance@localhost:5432/finance

# ── Ingestion ────────────────────────────────────────────────────────────────
INGESTION_SOURCE=csv
CSV_PATHS=data/sample/transactions.csv

# ── Plaid (only when INGESTION_SOURCE=plaid) ────────────────────────────────
# PLAID_CLIENT_ID=...
# PLAID_SECRET=...
# PLAID_ACCESS_TOKENS=token1,token2
# PLAID_ACCESS_TOKEN_OWNERS=Alex,Sam
# PLAID_BASE_URL=https://sandbox.plaid.com

# ── Google OAuth (required for dashboard) ───────────────────────────────────
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501/
GOOGLE_ALLOWED_EMAILS=email1@gmail.com,email2@gmail.com

# ── Supabase (optional — only if using Supabase instead of docker) ──────────
# SUPABASE_URL=https://yourproject.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=...

# ── ML artifacts (used in Phase 7, deferred) ────────────────────────────────
# MODEL_PATH=artifacts/classifier.joblib
# LABELED_DATASET_PATH=labeled_transactions.csv
```

### 1c. `pyproject.toml`
Replace the entire file with:
```toml
[build-system]
requires = ["setuptools>=70"]
build-backend = "setuptools.backends.legacy:build"

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
Make these targeted edits (do NOT rewrite; only fix the wrong parts):

- **Line 35** (Plaid sandbox bootstrap): change `python scripts/generate_public_token.py sandbox --append` → `python scripts/generate_sample_data.py` and `python scripts/create_sandbox_access_token.py --append`.
- **Lines 11-12** (Phase 1 status paragraph): remove "rolling burn-rate" and "household combined-vs-individual breakdowns" from the "not built" list. Rewrite to: "The dashboard implements all core views. Only ML is stubbed — the pipeline uses placeholders."
- **Lines 55-56** (Configuration section): remove `PlaidLinkConfig` (doesn't exist). Should read: `core/` — shared helpers: `config.py` (`load_settings()`, `ConfigError`), `auth_session.py`, `google_oauth.py`.
- **Line 59** (scripts bullet): remove `scripts/generate_public_token.py` reference; replace with `scripts/generate_sample_data.py` (Phase 2b).
- **Lines 72-75** (Automation section): replace "still on the dev branch and uncommitted" with "committed but inert until required Secrets are populated on the default branch."
- **Line 58** (dashboard description): remove "Altair" — the dashboard uses Plotly only.

---

## Phase 2 — Demo path

### 2a. CSV account enrichment (implement first — the dashboard is completely empty without this)

**Why this is critical**: `app/dashboard.py:328-331` builds the owner multiselect from `df["owner_name"].dropna().unique()`. When CSV data has NULL `owner_name`, the list is empty, and the mask at line 371 (`df["owner_name"].isin([])`) filters every row → the dashboard renders nothing.

#### File: `ingestion/csv_ingestor.py`

Add three new entries to `COLUMN_ALIASES` (after the existing `transaction_id` entry):
```python
COLUMN_ALIASES = {
    "date": ["date", "transaction_date", "posted_date", "posting_date"],
    "description": ["description", "name", "merchant", "memo"],
    "amount": ["amount", "transaction_amount", "value", "debit", "credit"],
    "balance": ["balance", "running_balance", "available_balance", "current_balance"],
    "account_name": ["account", "account_name", "account_id", "card_name"],
    "transaction_id": ["transaction_id", "id", "fitid", "reference", "unique_id"],
    # NEW — optional enrichment columns
    "owner_name": ["owner_name", "owner", "holder", "account_holder"],
    "account_type": ["account_type", "type"],
    "account_subtype": ["account_subtype", "subtype"],
}
```

In `_normalize_frame`, after the existing optional-column lookups (lines 42-44), add:
```python
owner_col = self._find_column(frame, "owner_name")
account_type_col = self._find_column(frame, "account_type")
account_subtype_col = self._find_column(frame, "account_subtype")
```

In the `pd.DataFrame({...})` constructor, extend the dict:
```python
"owner_name":      frame[owner_col].astype(str)        if owner_col        else pd.NA,
"account_type":    frame[account_type_col].astype(str)  if account_type_col  else pd.NA,
"account_subtype": frame[account_subtype_col].astype(str) if account_subtype_col else pd.NA,
```

Update the empty-frame fallback (line 80):
```python
return pd.DataFrame(columns=[
    "transaction_id", "date", "description", "amount", "balance",
    "account_name", "owner_name", "account_type", "account_subtype", "source"
])
```

**Note**: Do NOT add `owner_name`, `account_type`, or `account_subtype` to `dropna(subset=...)` — they are optional and absent from plain bank exports.

#### File: `database/db.py` — `upsert_accounts` method (lines 85-100)

Replace the entire method with a version that persists the enrichment columns:
```python
def upsert_accounts(self, frame: pd.DataFrame) -> None:
    sql = """
    INSERT INTO accounts (
        account_key, account_name, owner_name,
        account_type, account_subtype, balance_current, source
    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (account_key) DO UPDATE
    SET account_name    = EXCLUDED.account_name,
        owner_name      = COALESCE(EXCLUDED.owner_name,      accounts.owner_name),
        account_type    = COALESCE(EXCLUDED.account_type,    accounts.account_type),
        account_subtype = COALESCE(EXCLUDED.account_subtype, accounts.account_subtype),
        balance_current = COALESCE(EXCLUDED.balance_current, accounts.balance_current),
        source          = EXCLUDED.source,
        updated_at      = NOW()
    """
    cols = ["account_name", "source", "owner_name", "account_type", "account_subtype"]
    for col in cols:
        if col not in frame.columns:
            frame = frame.copy()
            frame[col] = pd.NA

    if "balance" in frame.columns and "date" in frame.columns:
        latest_balance = (
            frame.sort_values("date")
            .groupby("account_name", as_index=False)["balance"]
            .last()
            .rename(columns={"balance": "balance_current"})
        )
        accounts = (
            frame[cols]
            .drop_duplicates(subset=["account_name"])
            .merge(latest_balance, on="account_name", how="left")
        )
    else:
        accounts = frame[cols].drop_duplicates(subset=["account_name"]).copy()
        accounts["balance_current"] = pd.NA

    def _or_none(v):
        try:
            return None if pd.isna(v) else str(v)
        except (TypeError, ValueError):
            return str(v)

    rows = []
    for record in accounts.to_dict("records"):
        account_name = str(record["account_name"])
        source = str(record["source"])
        account_key = f"{source}:{account_name}"
        bal = record.get("balance_current")
        try:
            balance_current = None if pd.isna(bal) else float(bal)
        except (TypeError, ValueError):
            balance_current = None
        rows.append((
            account_key,
            account_name,
            _or_none(record.get("owner_name")),
            _or_none(record.get("account_type")),
            _or_none(record.get("account_subtype")),
            balance_current,
            source,
        ))
    if rows:
        self._execute_many(sql, rows)
```

`COALESCE(EXCLUDED.col, accounts.col)` ensures a plain bank CSV (no owner column) never nulls out metadata that was previously stored.

### 2b. Sample data generator

**Create `scripts/generate_sample_data.py`**

This is a deterministic generator (not a static committed CSV) because `run_pipeline` only fetches the trailing 90 days — a static CSV goes stale within weeks.

```
Usage: python scripts/generate_sample_data.py [--days 120] [--out data/sample]
Output: <out>/transactions.csv
Seed: random.seed(42)  — deterministic across runs
```

**Owners and accounts:**
| owner_name | account_name              | account_type | account_subtype |
|------------|---------------------------|--------------|-----------------|
| Alex       | Alex Chequing             | depository   | checking        |
| Alex       | Alex Rewards Visa         | credit       | credit card     |
| Alex       | Alex TFSA                 | investment   | tfsa            |
| Sam        | Sam Chequing              | depository   | checking        |
| Sam        | Sam High-Interest Savings | depository   | savings         |

**Sign convention**: positive amount = outflow (money leaving the account). This is the Plaid convention and is what `app/dashboard.py:387` assumes (`adjusted_amount = -amount`). State this clearly in the module docstring.

**Transaction patterns to generate:**
- Biweekly payroll: `amount = -2800` (negative = inflow), `description = "Payroll - Direct Deposit"`, on the 1st and 15th of each month. Alex → Alex Chequing, Sam → Sam Chequing.
- Monthly rent: `amount = 1350`, `description = "Rent"`, on the 1st, from Alex Chequing.
- Monthly utilities: `amount = 85`, `description = "Hydro - Utility Payment"`, on the 5th, from Sam Chequing.
- Monthly Netflix: `amount = 17.99`, `description = "Netflix.com"`, on the 12th, from Alex Rewards Visa.
- Monthly Spotify: `amount = 11.99`, `description = "Spotify Premium"`, on the 14th, from Sam Chequing.
- Biweekly groceries: `amount = uniform(80, 220)`, `description` = random choice of `["Whole Foods Market", "IGA Supermarché", "Provigo"]`, 2-3x per month per owner.
- Weekly restaurant/coffee: `amount = uniform(12, 65)`, `description` = random choice of `["Tim Hortons", "Starbucks Coffee", "Restaurant St-Denis", "Brasserie locale"]`, 1-2x per week per owner.
- Monthly transit: `amount = 100`, `description = "STM Opus Card"`, on the 2nd, from Sam Chequing.
- Weekly Uber: `amount = uniform(8, 35)`, `description = "Uber"`, 1x per week for Alex from Alex Rewards Visa.
- ATM withdrawals: `amount = choice([40, 60, 80, 100, 120])`, `description = "ATM Withdrawal"`, once or twice per month from chequing accounts.
- Monthly credit-card payment pair: On the 20th, post `amount = -350` to Alex Rewards Visa with `description = "Payment - Thank You"` AND `amount = 350` to Alex Chequing with `description = "Credit Card Payment"`. This exercises transfer-exclusion logic.
- 3 anomaly purchases spread across 120 days: amounts of $450, $890, $1200, descriptions like `"Electronics Store"`, `"Travel Agency"`, `"Appliance Purchase"`.

**Balance tracking**: maintain a running balance per account. Seed balances:
- Alex Chequing: 3500
- Alex Rewards Visa: 0 (credit — balance = amount owed, increases with purchases)
- Alex TFSA: 14000
- Sam Chequing: 4200
- Sam High-Interest Savings: 9800

After each transaction, update balance: `balance = prev_balance - amount` (for depository/investment); credit: `balance = prev_balance + amount` (positive purchases increase owed balance). Write current balance to `balance` column for each row.

**Output columns**: `date,description,amount,balance,account_name,owner,account_type,account_subtype,transaction_id`
- `date`: ISO format `YYYY-MM-DD`
- `transaction_id`: `f"SAMPLE-{i:05d}"` (zero-padded sequential)
- `owner` (not `owner_name`) — `COLUMN_ALIASES` maps `owner` → canonical `owner_name`

Sort by `date` ascending before writing.

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
      - "5432:5432"
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

No init SQL mount needed — `ensure_schema()` runs the migration DDL at runtime.

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
[Mermaid or ASCII: CSV/Plaid → pipeline/runner.py → DB → dashboard]

| Layer | Path | Responsibility |
|-------|------|----------------|
| Ingestion | ingestion/ | Fetch + normalize (CSV or Plaid) |
| Database | database/ | Idempotent upserts via sha256 hash; auto-run migrations |
| Analytics | analytics/ | ML classifier + outlier detector (placeholder in Phase 1) |
| Core | core/ | Config, Google OAuth/PKCE, session |
| Pipeline | pipeline/runner.py | Orchestrate ingest → classify → persist |
| App | app/ | Streamlit dashboard (4 tabs, bilingual EN/FR) |

Key design decisions (interview talking points):
- Hash-based idempotent upserts: sha256(account_name|date|description|amount) → safe to re-run daily
- Runtime migrations: ensure_schema() runs all database/migrations/*.sql sorted — no migration tooling
- Two-column category design: pipeline writes `category`; user edits write `user_category`; dashboard reads COALESCE
- OAuth+PKCE: full Google sign-in without a heavyweight framework; 4-hour session expiry
- Config precedence: env → .streamlit/secrets.toml → default via load_settings()
- Placeholder seam: swap build_placeholder_models() → build_models(settings) with no orchestration changes

## Quickstart (local with docker)
[verbatim from Phase 2 quickstart sequence]
Python 3.11+ required. Run all commands from repo root.

## Configuration reference
[Table from core/config.py — ONLY real vars, grouped]

## Ingesting your own data
CSV format + column aliases → docs/setup-database.md and docs/setup-plaid.md

## Project status & roadmap
✅ Data path: ingest → persist → dashboard
✅ Dashboard: 4 tabs, bilingual EN/FR, budgets, inline category editing
🔄 ML: classifier and outlier detector exist; pipeline uses placeholders (Phase 7)

## Contributing / License
```

### 4b. Create `docs/setup-google-oauth.md`

Steps:
1. GCP console → create project.
2. APIs & Services → OAuth consent screen → External → add your email as a test user.
3. Credentials → Create OAuth client ID → Web application.
4. Authorized redirect URIs: exactly `http://localhost:8501/` (must match `GOOGLE_OAUTH_REDIRECT_URI`).
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
| `INGESTION_SOURCE` | `plaid` or `csv` |
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
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -r requirements.txt
      - run: python -m unittest discover -s tests -v
```

No DB, network, or secrets needed — all tests are pure (mock everything).

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
4. Remove `CSV_PATHS` and `LABELED_DATASET_PATH` from env (no CSVs on runner; ML not wired).

---

## Phase 6 — Tests

All tests must be pure — no live DB, no network. Mock seam for DB: `@patch("database.db.psycopg.connect")`. All `pipeline.runner` deps patchable at `pipeline.runner.*`.

### 6a. `tests/test_db_upserts.py`

- `test_upsert_accounts_dedup` — frame with two rows for same account → one DB row.
- `test_upsert_accounts_key_derivation` — account_key = `"source:account_name"`.
- `test_upsert_accounts_owner_enrichment` — frame with owner/type/subtype/balance → SQL params include all four.
- `test_upsert_accounts_no_owner_is_none` — frame without `owner_name` column → owner param is `None`.
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

Patches: `pipeline.runner.load_settings`, `pipeline.runner.CSVIngestor`, `pipeline.runner.PlaidIngestor`, `pipeline.runner.DatabaseClient`.

- `test_build_ingestor_csv` — source `csv` → `CSVIngestor`.
- `test_build_ingestor_plaid` — source `plaid` → `PlaidIngestor`.
- `test_build_ingestor_plaid_missing_creds` — plaid + no client_id → `ConfigError`.
- `test_run_pipeline_happy_path` — non-empty frame → `upsert_categories` and `upsert_transactions` called; frame has `category` (str) and `is_outlier` (bool) columns.
- `test_run_pipeline_empty_frame` — empty frame → no DB calls; returns empty DataFrame.
- `test_run_pipeline_csv_calls_upsert_accounts` — csv source → `upsert_accounts` called, `upsert_plaid_accounts` not called.
- `test_run_pipeline_plaid_calls_upsert_plaid_accounts` — plaid source → `upsert_plaid_accounts` called, `upsert_accounts` not called.

### 6c. `tests/test_config.py`

Use `@patch("core.config.load_dotenv")` + `@patch.dict(os.environ, {...}, clear=True)`.

- `test_database_url_required` — no `DATABASE_URL` → `ConfigError`.
- `test_ingestion_source_default` — no `INGESTION_SOURCE` → `"csv"`.
- `test_invalid_ingestion_source` — `INGESTION_SOURCE=ftp` → `ConfigError`.
- `test_csv_paths_required_for_csv` — csv + no `CSV_PATHS` → `ConfigError`.
- `test_csv_paths_split` — `CSV_PATHS=a.csv,b.csv` → `["a.csv", "b.csv"]`.
- `test_env_over_secrets_precedence` — env value beats secrets.toml value.
- `test_google_allowed_emails_split` — `GOOGLE_ALLOWED_EMAILS=a@b.com,c@d.com` → list of two.
- `test_plaid_access_token_owners_split` — comma-separated → list.

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

### 6f. `tests/test_sample_data.py`

```python
import tempfile, subprocess, sys
from pathlib import Path
from datetime import date, timedelta
```

- `test_generator_produces_output` — run generator into tempdir; assert CSV exists and has >100 rows.
- `test_generator_both_owners_present` — load CSV; assert `{"Alex", "Sam"}` ⊆ unique values in `owner` column.
- `test_generator_output_survives_csv_ingestor` — feed through `CSVIngestor.fetch_transactions(start=today-125d, end=today)`; result not empty; `"owner_name"` in columns; at least one non-null owner.
- `test_generator_idempotent` — run twice into separate dirs; file contents identical.

### 6g. Extend `tests/test_csv_ingestor.py`

- `test_normalize_with_owner_column` — CSV with `owner` column → normalized has `owner_name` with values.
- `test_normalize_with_account_type_column` — `account_type` preserved.
- `test_normalize_without_optional_columns` — only date/description/amount → `owner_name` is `pd.NA`, no exception.
- `test_missing_required_column_raises` — CSV missing `description` → `ValueError`.

---

## Phase 7 — DEFERRED: ML activation

Explicitly out of initial publish scope. Do after Phases 1-6 land and the repo is public.

- [ ] `core/config.py`: add `ML_MODE` (`placeholder` | `real`, default `placeholder`) to `Settings` + `.env.example`.
- [ ] Create `analytics/models.py::build_models(settings) -> ModelBundle`: returns placeholder or `TransactionClassifier(settings.model_path)` + `OutlierDetector()` — both share the same duck-type interface (`categorize(Series)` / `score(DataFrame)`).
- [ ] `pipeline/runner.py:44`: `build_placeholder_models()` → `build_models(settings)`.
- [ ] Create `scripts/train_classifier.py`: loads settings, calls `TransactionClassifier.train(labeled_dataset_path)`, prints holdout accuracy. Rule-based fallback means `ML_MODE=real` degrades gracefully untrained.
- [ ] Implement `scripts/generate_sample_data.py --labeled` flag: writes `data/sample/labeled_transactions.csv` (`description,category`) from the same merchant pool → train → pipeline → categorized dashboard in 3 commands.
- [ ] Tests: extend `test_classifier.py` (train on synthetic, assert accuracy > 0.5); add `tests/test_models_builder.py` (mode switch).
- [ ] Update README roadmap.

---

## Ordering constraints / risks

1. Phase 2a (CSV enrichment) **before** running the sample data generator.
2. `.gitignore data/` (Phase 1a) **before** generating anything into `data/`.
3. Phase 3a (`_classify_tx_type` fix) **before** all other Phase 3 sections.
4. Phase 3b (DB methods) **before** Phases 3k and 3l.
5. Phase 3c (migrations) **before** Phase 3d (`ensure_schema` iteration) — 3d relies on the files existing.
6. Phase 3e (SELECT query with COALESCE + `transaction_hash`) **before** Phase 3l (ledger edit).
7. Fix case in `analytics/placeholders.py` (`"uncategorized"` → `"Uncategorized"`) **alongside** Phase 3c, before running the pipeline against the seeded categories.
8. **Never** change `build_transaction_hash` inputs — re-ingest idempotency depends on them.
9. Sample data must use Plaid sign convention (positive = outflow) or cash flow inverts.
10. Cron goes live only after merge to `main` + GitHub Secrets — Phase 0 owner action, not code.

---

## Verification

1. `python -m unittest discover -s tests -v` — all green on Python 3.11 and 3.12.
2. `docker compose up -d && python scripts/generate_sample_data.py && python main.py` — no errors; rows in DB.
3. Run `python main.py` a second time — row count unchanged (idempotency).
4. `streamlit run app/streamlit_app.py` — sign in with Google; all 4 tabs render; Overview/Net worth/Cash flow/Budget sections populate; Transactions tab shows ledger with category dropdown populated from DB canonical list; category edit persists on page refresh; anomaly section shows empty-state (expected — placeholders).
5. Filter the sidebar to a past month → Budget tab shows that month's spending; "Projected EOM" is replaced by "Actual".
6. `pip install -e .` in a fresh venv → same deps as `pip install -r requirements.txt`.
7. Push branch → CI runs green on 3.11 + 3.12.
8. `git grep -E "jacos|jacosse|lapointe|gmail\.com|C:\\\\Users"` → no matches.
