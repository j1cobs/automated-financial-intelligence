"""FastAPI app entrypoint. Run locally with:

uvicorn api.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import DatabaseClient

from .deps import get_settings
from .routers import auth as auth_router
from .routers import data as data_router

_settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run every pending migration exactly once at process startup — not per-request (see
    `api/deps.py::get_db`, which deliberately does NOT do this). `app/` (Streamlit) has always
    relied on the pipeline or seed script having been run against a database at least once
    first; `api/` is often the *first* process to touch a fresh/local database, so it can't
    make that same assumption. `ensure_schema()`'s migrations are idempotent (CLAUDE.md), so
    this is safe to run on every boot, including redeploys. Let a failure here propagate —
    the app should refuse to start against a broken DATABASE_URL rather than boot and 500 on
    the first request.
    """
    DatabaseClient(_settings.database_url).ensure_schema()
    yield


app = FastAPI(title="Automated Financial Intelligence API", lifespan=lifespan)

# Exact-match allow-list only — never "*" — since cookies must cross origins here
# (web and api are hosted on different platform subdomains, no shared parent domain).
_allow_origins = [_settings.frontend_origin] if _settings.frontend_origin else []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(data_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
