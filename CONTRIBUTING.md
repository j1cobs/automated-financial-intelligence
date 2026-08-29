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

> **Python version matters when regenerating.** `pip-compile` resolves against the interpreter it runs
> on and does **not** emit `; python_version` markers, so the lock is only installable on that version
> and newer. The current lock was generated on **Python 3.13** and pins `numpy`/`scipy` that require
> **>=3.12** — which is why the supported floor is 3.12 (`pyproject.toml`) and CI tests 3.12 and 3.13.
> Regenerate on 3.13, and if you ever lower the floor, re-run `pip-compile` on the *lowest* version you
> intend to support.

## Running things

```bash
python -m unittest discover -s tests -v      # tests
python main.py                                # pipeline (needs Plaid + DB credentials)
streamlit run streamlit_app.py                 # Streamlit dashboard (needs DB + Google OAuth credentials)
python scripts/seed_sample_data.py             # demo data, no credentials needed beyond DATABASE_URL
uvicorn api.main:app --reload                  # API for the React dashboard
cd web && npm run dev                          # React dashboard (needs the API running)
cd web && npm run test && npx tsc -b && npm run lint && npm run format:check  # web checks, all four must pass
```

## Linting and formatting

Lint/format is handled by [ruff](https://docs.astral.sh/ruff/), a dev-only tool — it is deliberately
absent from `requirements.txt`/`requirements.lock` since it's not a runtime dependency.

```bash
pip install ruff==0.15.22
ruff check .              # lint
ruff check --fix .        # lint, applying safe autofixes
ruff format .             # format
```

Config lives in `pyproject.toml` (`[tool.ruff]` / `[tool.ruff.lint]`). CI runs `ruff check .` and
`ruff format --check .` in a dedicated `lint` job and fails the build on any violation — there is no
soft-launch period.

## Conventions

- **No personal data in the repo.** No hardcoded accounts, emails, tokens, or file paths. Every credential and tunable goes through `core/config.py::load_settings()`, sourced from environment variables, `.env`, or `.streamlit/secrets.toml`. New config belongs in `Settings` and `.env.example`, not inline.
- **Layer boundaries are strict.** `ingestion/`, `database/`, `analytics/`, `app/`, `core/`, and `pipeline/` each own one responsibility. A change in one shouldn't need to reach into another. If it does, that's usually a sign the change belongs somewhere else.
- **Run everything from the repo root.** `database/db.py` reads the migration files with a path relative to the working directory, and config loading does the same for `.env` / `.streamlit/secrets.toml`.

## Known issue

`pd.read_sql` in `app/dashboard.py` is called on a raw `psycopg` connection, which pandas warns is only tested with SQLAlchemy connections. It works fine in practice; the warning is cosmetic and not on the priority list to silence right now.

## Before opening a PR

- Tests pass locally.
- `ruff check .` and `ruff format --check .` both pass.
- No personal data (real account names, emails, tokens) anywhere in the diff.
- New config variables are documented in `.env.example` and the README's configuration table.
