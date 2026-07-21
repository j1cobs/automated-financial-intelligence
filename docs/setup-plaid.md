# Setting up Plaid

Plaid credentials are only needed to run the actual ingestion pipeline (`python main.py`). The dashboard and the sample-data seed script don't need them at all.

## Sandbox (for development)

Run the bootstrap script, which walks through Plaid's sandbox flow and mints an access token for you:

```bash
python scripts/create_sandbox_access_token.py --append
```

`--append` writes the token straight into `.env` (gitignored). Without it, the script prints only the last six characters of the token to stdout. Pass `--print-token` if you need the full value for a manual copy.

Repeat this once per account you want to simulate, then set `PLAID_ACCESS_TOKEN_OWNERS` so each token is labeled with whose account it represents. The two lists are matched by position:

```env
PLAID_ACCESS_TOKENS=access-sandbox-aaa,access-sandbox-bbb
PLAID_ACCESS_TOKEN_OWNERS=Alex,Sam
```

`pipeline/runner.py` raises a config error if the two lists are set but have different lengths, since a silent misalignment would mislabel whose transactions are whose.

## Production

Set `PLAID_BASE_URL` to Plaid's production endpoint and swap in production tokens. This repo has no Plaid Link UI. Tokens are expected to be minted externally (Plaid's own Link quickstart, or your own Link integration) and dropped into `PLAID_ACCESS_TOKENS`.
