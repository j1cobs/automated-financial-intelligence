# automated-financial-intelligence

A modular, end-to-end, serverless-ready personal finance platform in Python. The project ingests bank transactions (Plaid or CSV), stores normalized data in PostgreSQL, classifies transactions with ML, flags anomalies, and exposes a secure Streamlit dashboard.

## Architecture

- `ingestion/`
  - `base.py`: abstract `BaseIngestor` interface
  - `plaid_ingestor.py`: paginated Plaid `/transactions/get` integration for multiple access tokens
  - `csv_ingestor.py`: robust schema-normalizing CSV fallback ingestion
- `database/`
  - `migrations/001_core_tables.sql`: idempotent schema for `accounts`, `transactions`, `categories`
  - `db.py`: schema bootstrapping + idempotent upserts via unique transaction hash
- `analytics/`
  - `classifier.py`: TF-IDF + Linear SVM training/inference with rule-based fallback
  - `outlier_detector.py`: per-category anomaly scoring via Isolation Forest and z-score fallback
- `main.py`
  - headless orchestration script (ingest → classify → outlier detect → sync)
- `.github/workflows/daily-finance-pipeline.yml`
  - daily cron-based automation with GitHub Secrets injection
- `app/streamlit_app.py`
  - authenticated dashboard with responsive Plotly/Altair views

## Configuration & Secrets

Use environment variables or `.streamlit/secrets.toml`.

### Required

- `DATABASE_URL`: PostgreSQL URL (Supabase/Neon compatible)

### Ingestion

- `INGESTION_SOURCE`: `plaid` or `csv` (default: `csv`)
- `CSV_PATHS`: comma-separated local CSV file paths
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `PLAID_ACCESS_TOKENS`: comma-separated Plaid access tokens
- `PLAID_BASE_URL`: defaults to `https://sandbox.plaid.com`

### ML

- `MODEL_PATH`: serialized model output path (default: `artifacts/classifier.joblib`)
- `LABELED_DATASET_PATH`: labeled data CSV path (default: `labeled_transactions.csv`)

### Dashboard Security

- `ALLOWED_EMAILS`: comma-separated whitelist of authorized emails
- `DASHBOARD_PASSWORD`: shared password for session-state login

## Local Setup

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run Pipeline

```bash
python main.py
```

## Run Dashboard

```bash
streamlit run app/streamlit_app.py
```

## Train Classifier

If `MODEL_PATH` does not exist, `main.py` attempts to train using `LABELED_DATASET_PATH`.
Expected columns in labeled CSV:

- `description`
- `category`

If training/model loading fails, the system falls back to rule-based regex categorization.

## Testing

```bash
python -m unittest discover -s tests -v
```

## GitHub Actions Automation

The workflow `.github/workflows/daily-finance-pipeline.yml` runs daily at 07:00 UTC and supports manual trigger (`workflow_dispatch`).
Store all runtime credentials in repository GitHub Secrets.
