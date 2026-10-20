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

Google OAuth secrets are **not** needed here. They're only used by the API process, which this workflow never runs.

You can trigger a manual run from the Actions tab (`workflow_dispatch`) without waiting for the schedule, which is the fastest way to confirm Secrets are wired up correctly before relying on the cron.

## Dashboard (Vercel + Render)

The dashboard is two deployables, both separate from the pipeline:

- **`web/`** (the React app) on Vercel, with `web/` as the project root. The browser only ever calls the relative `/api` prefix, and `web/vercel.json` rewrites `/api/*` to the API service (`https://<your-service>.onrender.com/:path*`). Change the rewrite's `destination` to your own service. The web build takes no environment variables: the API base is fixed to `/api` in `web/src/lib/api.ts`.
- **`api/`** (FastAPI) on Render, started with `uvicorn api.main:app`, bound to the host and port the platform provides. It runs every migration at boot (`ensure_schema()`) and exposes `GET /health`.

Because of the rewrite, the browser talks to a single origin (your Vercel one), so the API's `SameSite=None; Secure` session cookie is first-party to it. This is what keeps iOS Safari from blocking the sign-in. It only works if the OAuth callback also goes through the rewrite (see `GOOGLE_OAUTH_REDIRECT_URI` below).

Environment variables for the API service (all read by `core/config.py::load_settings()`):

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Required; the process refuses to start without it |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Sign-in fails without them |
| `GOOGLE_OAUTH_REDIRECT_URI` | `https://<your-app>.vercel.app/api/auth/google/callback`: the Vercel origin plus `/api`, not the Render URL, so the callback goes through the rewrite and the cookie is set on the Vercel origin. The API route itself is `/auth/google/callback`. Must be registered verbatim in the Google console ([setup-google-oauth.md](setup-google-oauth.md)) |
| `GOOGLE_ALLOWED_EMAILS` | Comma-separated; empty means nobody can sign in |
| `JWT_SECRET` | Signs the session cookie; without it no session is minted |
| `FRONTEND_ORIGIN` | `https://<your-app>.vercel.app`: the CORS allow-list entry and where the browser is sent after sign-in. Read once at startup, so restart after changing it |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ACCESS_TOKENS`, `PLAID_BASE_URL`, `PLAID_ACCESS_TOKEN_OWNERS` | Needed only for `POST /accounts/refresh-balances`, which calls Plaid (503 if credentials or tokens are unset). `PLAID_ACCESS_TOKEN_OWNERS` is optional and `PLAID_BASE_URL` defaults to the Plaid sandbox, so set it for production Plaid |

Mismatches between `GOOGLE_OAUTH_REDIRECT_URI`, the URI registered in the Google console, and the rewrite are the most common cause of a broken sign-in after deploying.
