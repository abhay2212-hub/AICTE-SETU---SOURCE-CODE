# Owner: Dev A
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock
from app.models.auth import User
from app.models.blind_match import BlindMatchCase, EncodeRequest, EncodeResponse
from app.services import blind_match as service

router = APIRouter(prefix="/blind-match", tags=["blind-match"])
CASE_READERS = require_roles("aicte_admin", "auditor", "institution_admin", "institution_operator")


@router.post(
    "/encode",
    response_model=EncodeResponse,
    dependencies=[Depends(require_roles("aicte_admin"))],
)
def encode(body: EncodeRequest) -> dict:
    """Demo only: show what a Bloom-filter encoding looks like. Never stores input."""
    return mock("blind_match_encode")


@router.get("/cases", response_model=list[BlindMatchCase])
def cases(
    user: User = Depends(CASE_READERS),
    real: bool = Depends(source("blind_match")),
) -> list[dict]:
    """Institution users see only cases involving their institution, the other side hidden."""
    if real:
        with transaction() as conn:
            return service.list_cases(conn, user)
    return service.fixture_cases(mock("blind_match_cases"), user)
