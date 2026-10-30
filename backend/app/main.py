# Owner: Dev B
"""FastAPI application: CORS, mock-mode header and every router."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.datasource import all_real
from app.core.db import close_pool, warm_pool
from app.routers import (
    admissions,
    audit,
    auth,
    batches,
    blind_match,
    blind_match_scan,
    certificates,
    credentials,
    engine,
    health,
    institutions,
    integrations,
    integrity,
    internal,
    public,
    reports,
    review_cases,
    seat_ledger,
    students,
    submission_windows,
    validation_issues,
    webhooks,
)

settings = get_settings()
settings.real_domain_set  # noqa: B018  (fail fast on a misspelled REAL_DOMAINS value)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    warm_pool()
    yield
    close_pool()


app = FastAPI(
    title="APAAR Integrity Platform",
    description="Verifiable, consent-first student records for AICTE-approved institutions.",
    version=health.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Mock", "X-Certificate-Id"],
)


@app.middleware("http")
async def mock_header(request: Request, call_next):
    """X-Mock: true when the response came from fixtures, false when it came from Postgres.

    Domain routers record their source in request.state; other endpoints report false only
    when every domain is real.
    """
    response = await call_next(request)
    default = "false" if all_real() else "true"
    response.headers["X-Mock"] = getattr(request.state, "x_mock", default)
    return response


for module in (
    health,
    engine,
    auth,
    institutions,
    seat_ledger,
    batches,
    validation_issues,
    admissions,
    submission_windows,
    review_cases,
    audit,
    integrations,
    internal,
    public,
    integrity,
    blind_match,
    blind_match_scan,
    reports,
    certificates,
    credentials,
    students,
    webhooks,
):
    app.include_router(module.router)
