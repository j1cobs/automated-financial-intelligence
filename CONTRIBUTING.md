# Contributing

## Setup

```bash
python -m pip install --upgrade pip
pip install --require-hashes -r requirements.lock
```

`requirements.lock` is generated from `requirements.txt` with `pip-compile --generate-hashes`. If you need to add or change a dependency, edit `requirements.txt`, then regenerate the lock:

```bash
pip install pip-tools
pip-compile --generate-hashes --output-file=requirements.lock requirements.txt
```

Commit both files together.

## Running things

```bash
python -m unittest discover -s tests -v      # tests
python main.py                                # pipeline (needs Plaid + DB credentials)
streamlit run app/streamlit_app.py             # dashboard (needs DB + Google OAuth credentials)
python scripts/seed_sample_data.py             # demo data, no credentials needed beyond DATABASE_URL
```

## Conventions

- **No personal data in the repo.** No hardcoded accounts, emails, tokens, or file paths. Every credential and tunable goes through `core/config.py::load_settings()`, sourced from environment variables, `.env`, or `.streamlit/secrets.toml`. New config belongs in `Settings` and `.env.example`, not inline.
- **Layer boundaries are strict.** `ingestion/`, `database/`, `analytics/`, `app/`, `core/`, and `pipeline/` each own one responsibility. A change in one shouldn't need to reach into another. If it does, that's usually a sign the change belongs somewhere else.
- **Run everything from the repo root.** `database/db.py` reads the migration files with a path relative to the working directory, and config loading does the same for `.env` / `.streamlit/secrets.toml`.

## Known issue

`pd.read_sql` in `app/dashboard.py` is called on a raw `psycopg` connection, which pandas warns is only tested with SQLAlchemy connections. It works fine in practice; the warning is cosmetic and not on the priority list to silence right now.

## Before opening a PR

- Tests pass locally.
- No personal data (real account names, emails, tokens) anywhere in the diff.
- New config variables are documented in `.env.example` and the README's configuration table.
