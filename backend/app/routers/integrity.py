# Owner: Dev A
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.integrity import IntegrityDetail, IntegrityRanking
from app.services import integrity_store

router = APIRouter(
    prefix="/integrity",
    tags=["integrity"],
    dependencies=[Depends(require_roles("aicte_admin", "auditor"))],
)

REAL = source("integrity")


@router.get("/institutions", response_model=list[IntegrityRanking])
def ranked_institutions(real: bool = Depends(REAL)) -> list[dict]:
    """Institutions ranked lowest integrity score first."""
    if real:
        with transaction() as conn:
            return integrity_store.latest_rankings(conn)
    return mock("integrity_ranking")


@router.get("/institutions/{institution_id}", response_model=IntegrityDetail)
def institution_integrity(institution_id: str, real: bool = Depends(REAL)) -> dict:
    """Signals and anomaly explanation for one institution."""
    if real:
        with transaction() as conn:
            detail = integrity_store.latest_detail(conn, institution_id)
        if detail is None:
            raise not_found("Institution", institution_id)
        return detail
    detail = mock("integrity_details").get(institution_id)
    if detail is None:
        raise not_found("Institution", institution_id)
    return detail
