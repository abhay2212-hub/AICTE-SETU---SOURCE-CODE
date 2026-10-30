# Owner: Dev B
"""Unauthenticated aggregates for the landing page. Counts only, never names or IDs."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.audit import verify_chain
from app.core.config import get_settings
from app.core.datasource import mark_source
from app.core.db import transaction
from app.mocks import mock
from app.models.public import PublicStats
from app.services import audit_store

router = APIRouter(prefix="/public", tags=["public"])

ACADEMIC_YEAR = "2026-27"
# Each count follows the switch of the domain it comes from.
STAT_DOMAINS = ("institutions", "admissions", "review_cases", "audit")


def _count(conn, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()["n"])


def _real_stat(conn, name: str):
    if name == "institutions":
        return _count(conn, "select count(*) as n from public.institutions")
    if name == "admissions":
        return _count(
            conn,
            "select count(*) as n from public.admissions where active and academic_year = %s",
            (ACADEMIC_YEAR,),
        )
    if name == "review_cases":
        return _count(conn, "select count(*) as n from public.review_cases where status = 'open'")
    return audit_store.verify(conn)


def _fixture_stat(name: str):
    if name == "institutions":
        return len(mock("institutions"))
    if name == "admissions":
        # The enrolment report fixture holds the platform-wide active admission total.
        return mock("enrolment_report")["state"]["total"]
    if name == "review_cases":
        return sum(1 for c in mock("review_cases") if c["status"] == "open")
    events = mock("audit_events")
    return {"ok": verify_chain(events) is None, "checked": len(events)}


@router.get("/stats", response_model=PublicStats)
def public_stats(request: Request) -> dict:
    """Institution, admission, open case and audit chain totals. No sign-in needed."""
    settings = get_settings()
    real = {name for name in STAT_DOMAINS if settings.is_real(name)}
    if real:
        with transaction() as conn:
            stats = {name: _real_stat(conn, name) for name in real}
    else:
        stats = {}
    for name in STAT_DOMAINS:
        if name not in real:
            stats[name] = _fixture_stat(name)
    # X-Mock is false only when every number came from Postgres.
    mark_source(request, real == set(STAT_DOMAINS))
    audit = stats["audit"]
    return {
        "institutions": stats["institutions"],
        "active_admissions": stats["admissions"],
        "open_review_cases": stats["review_cases"],
        "audit_chain_ok": audit["ok"],
        "audit_events": audit["checked"],
        "academic_year": ACADEMIC_YEAR,
    }
