# Owner: Dev B
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.seat_ledger import SeatLedger
from app.services import seat_ledger as service

router = APIRouter(tags=["seat-ledger"])

READERS = require_roles("aicte_admin", "auditor", "institution_admin", "institution_operator")


@router.get("/institutions/{institution_id}/seat-ledger", response_model=SeatLedger)
def get_seat_ledger(
    institution_id: str,
    academic_year: str = Query("2026-27"),
    user: User = Depends(READERS),
    real: bool = Depends(source("seat_ledger")),
) -> dict:
    """Per programme and pool: approved_seats, admitted (used), available (remaining),
    overrun and rule_version."""
    if real:
        with transaction() as conn:
            return service.get_ledger(conn, institution_id, academic_year, user)
    ledger = mock("seat_ledger").get(institution_id)
    if ledger is None or ledger["academic_year"] != academic_year:
        raise not_found("Seat ledger", f"{institution_id}/{academic_year}")
    return ledger
