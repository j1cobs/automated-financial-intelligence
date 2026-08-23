"""FastAPI app entrypoint. Run locally with:

uvicorn api.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import get_settings
from .routers import auth as auth_router
from .routers import data as data_router

app = FastAPI(title="Automated Financial Intelligence API")

_settings = get_settings()

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
