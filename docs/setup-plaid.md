# Setting up Plaid

Plaid credentials are only needed to run the actual ingestion pipeline (`python main.py`). The dashboard and the sample-data seed script don't need them at all.

Both sandbox and production tokens are minted with the same tool, `scripts/plaid_link.py`, which is environment-aware off `PLAID_BASE_URL`.

## Sandbox (for development)

```bash
python scripts/plaid_link.py create --append
```

With `PLAID_BASE_URL` unset or pointed at Plaid's sandbox endpoint, this mints a token headlessly — no browser, via Plaid's `/sandbox/public_token/create` shortcut — and exchanges it for an access token.

`--append` writes the token straight into `.env` (gitignored). Without it, the script prints only the last six characters of the token to stdout. Pass `--print-token` if you need the full value for a manual copy.

Repeat this once per account you want to simulate, passing `--owner NAME` each time so `PLAID_ACCESS_TOKEN_OWNERS` stays aligned by position with `PLAID_ACCESS_TOKENS`:

```env
PLAID_ACCESS_TOKENS=access-sandbox-aaa,access-sandbox-bbb
PLAID_ACCESS_TOKEN_OWNERS=Alex,Sam
```

`pipeline/runner.py` raises a config error if the two lists are set but have different lengths, since a silent misalignment would mislabel whose transactions are whose — `append_token_to_env` in `scripts/plaid_link.py` enforces this itself, refusing a write that would create a mismatch.

## Production

```bash
python scripts/plaid_link.py create --append
```

With `PLAID_BASE_URL` pointed at Plaid's production endpoint, this opens Plaid Link in your default browser (a throwaway local server on `127.0.0.1`) to complete the real bank login/MFA, then exchanges the resulting token. No `redirect_uri` is configured or needed — Plaid only requires one for mobile clients, so plain HTTP on localhost works for desktop Link, including OAuth institutions like Chase.

As with sandbox, pass `--print-token` to get the full value for the GitHub Actions `PLAID_ACCESS_TOKENS` secret — `.env` only affects local runs, not the daily workflow.

### Repairing a broken Item

If the daily pipeline starts failing with a Plaid `ITEM_ERROR` such as `NO_ACCOUNTS` or `ITEM_LOGIN_REQUIRED`, re-authenticate the existing Item instead of minting a new token:

```bash
python scripts/plaid_link.py repair
```

This lists every configured token with its live status, lets you pick which one to fix, and opens Plaid Link in **update mode** (`create_link_token(access_token=...)` in `ingestion/plaid_link.py`) so you can re-complete the bank login. Update mode does not change the access token — nothing needs to be written back to `.env` or GitHub Secrets. Pass `--token-suffix` to skip the interactive picker if you already know which token (e.g. from a failure log).
