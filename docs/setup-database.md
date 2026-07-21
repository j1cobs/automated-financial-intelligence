# Setting up the database

`ensure_schema()` runs every file in `database/migrations/` in order, every time the app or pipeline starts. Each migration is written to be safe to run more than once, so there's no separate migration step to remember. Pick any of the three options below and set `DATABASE_URL` accordingly.

## Docker (default, no account needed)

```bash
docker compose up -d
```

This starts a local Postgres container bound to `127.0.0.1:5433`, not the default 5432 (chosen to avoid clashing with a Postgres install already running on the host). It matches the default `DATABASE_URL` in `.env.example`, so no further configuration is needed. The port is bound to loopback only; the demo credentials (`finance` / `finance`) are not meant to be reachable from the network.

## Supabase

Use the connection pooler URL, not the direct connection. It's on port `6543`:

```env
DATABASE_URL=postgresql://user:pass@host.pooler.supabase.com:6543/postgres
```

Supabase encrypts data at rest by default; no extra configuration needed there.

## Neon

Neon requires an explicit `sslmode`, though `enforce_tls()` in `core/config.py` will append `sslmode=require` automatically for any non-local host if you forget:

```env
DATABASE_URL=postgresql://user:pass@host.neon.tech/dbname?sslmode=require
```
