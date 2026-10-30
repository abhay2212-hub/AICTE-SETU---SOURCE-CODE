# Owner: Dev B
"""Full cross-institution Blind Match rescan (app.services.blind_match.scan_all)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.models.blind_match import BlindMatchScanResult
from app.services import blind_match, realtime

router = APIRouter(prefix="/admin/blind-match", tags=["admin"])


@router.post(
    "/scan",
    response_model=BlindMatchScanResult,
    dependencies=[Depends(require_roles("aicte_admin"))],
)
def scan(background: BackgroundTasks, real: bool = Depends(source("blind_match"))) -> dict:
    """Encode students that have no encoding yet and compare every DOB block across
    institutions. Idempotent: a student pair never gets a second case."""
    if real:
        with transaction() as conn:
            result = blind_match.scan_all(conn)
        background.add_task(realtime.publish, result.pop("events", []))
        return result
    return {"students_encoded": 0, "candidates": 0, "matches": 0, "cases_created": []}
