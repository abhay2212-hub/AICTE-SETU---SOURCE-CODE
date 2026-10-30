# Owner: Dev B
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.common import CaseKind, CaseStatus
from app.models.review_cases import ResolveRequest, ReviewCase
from app.services import realtime
from app.services import review_cases as service

router = APIRouter(prefix="/review-cases", tags=["review-cases"])

READERS = require_roles("aicte_admin", "auditor", "institution_admin")
RESOLVERS = require_roles("aicte_admin")
REAL = source("review_cases")


@router.get("", response_model=list[ReviewCase])
def list_review_cases(
    kind: CaseKind | None = None,
    status: CaseStatus | None = None,
    user: User = Depends(READERS),
    real: bool = Depends(REAL),
) -> list[dict]:
    if real:
        with transaction() as conn:
            return service.list_cases(conn, user, kind, status)
    return [
        c
        for c in mock("review_cases")
        if (kind is None or c["kind"] == kind) and (status is None or c["status"] == status)
    ]


def _mock_case(case_id: str) -> dict:
    case = next((c for c in mock("review_cases") if c["id"] == case_id), None)
    if case is None:
        raise not_found("Review case", case_id)
    return case


@router.get("/{case_id}", response_model=ReviewCase)
def get_review_case(
    case_id: str, user: User = Depends(READERS), real: bool = Depends(REAL)
) -> dict:
    if real:
        with transaction() as conn:
            return service.get_case(conn, case_id, user)
    return _mock_case(case_id)


@router.post("/{case_id}/resolve", response_model=ReviewCase)
def resolve_review_case(
    case_id: str,
    body: ResolveRequest,
    background: BackgroundTasks,
    user: User = Depends(RESOLVERS),
    real: bool = Depends(REAL),
) -> dict:
    """Set the outcome with a required, non-empty reviewer note."""
    if real:
        with transaction() as conn:
            case, event = service.resolve_case(conn, case_id, body.status, body.note, user)
        background.add_task(realtime.publish, [event])
        return case
    case = _mock_case(case_id)
    now = datetime.now(UTC).isoformat()
    case.update(status=body.status, reviewer_note=body.note, updated_at=now)
    if body.status in ("confirmed", "dismissed"):
        case["resolved_at"] = now
    return case
