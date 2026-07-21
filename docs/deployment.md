# Deployment

## GitHub Actions (daily pipeline)

`.github/workflows/daily-finance-pipeline.yml` runs `python main.py` on a daily cron. It only activates once two things are both true: the workflow file is on `main` (GitHub only schedules workflows from the default branch), and the Secrets below are populated on the repository.

| Secret | Notes |
|---|---|
| `DATABASE_URL` | Required |
| `PLAID_CLIENT_ID` | Required to ingest |
| `PLAID_SECRET` | Required to ingest |
| `PLAID_ACCESS_TOKENS` | Comma-separated |
| `PLAID_ACCESS_TOKEN_OWNERS` | Comma-separated, positionally aligned with `PLAID_ACCESS_TOKENS` |
| `PLAID_BASE_URL` | Optional, defaults to the Plaid sandbox endpoint |

Google OAuth secrets are **not** needed here. They're only read by the dashboard process, which this workflow never runs.

You can trigger a manual run from the Actions tab (`workflow_dispatch`) without waiting for the schedule, which is the fastest way to confirm Secrets are wired up correctly before relying on the cron.

## Dashboard

The dashboard (`streamlit run app/streamlit_app.py`) is a separate process from the pipeline and needs its own environment: `DATABASE_URL` plus the `GOOGLE_OAUTH_*` and `GOOGLE_ALLOWED_EMAILS` variables. If you're deploying to Streamlit Community Cloud or similar, set `GOOGLE_OAUTH_REDIRECT_URI` to the deployed HTTPS URL and make sure that same URL is registered in the Google Cloud console (see [setup-google-oauth.md](setup-google-oauth.md)). Mismatches here are the most common cause of a broken sign-in after deploying.
