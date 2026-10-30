# Owner: Dev B
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.core.config import Settings, get_settings
from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles, scoped_institution
from app.mocks import mock, not_found
from app.models.admissions import (
    Admission,
    EditableField,
    EditDecision,
    EditRequest,
    EditRequestCreate,
    EditRequestStatus,
    WithdrawRequest,
)
from app.models.auth import User
from app.models.common import AdmissionStatus, SeatPool
from app.models.student_responses import MarkNoResponseRequest, MarkNoResponseResult
from app.services import admissions as service
from app.services import realtime, student_responses

router = APIRouter(tags=["admissions"])

READERS = require_roles("aicte_admin", "auditor", "institution_admin", "institution_operator")
EDITORS = require_roles("institution_admin", "institution_operator")
DECIDERS = require_roles("aicte_admin")
WITHDRAWERS = require_roles("institution_admin")
REAL = source("admissions")
# Realtime broadcast requests are kept small when many admissions change at once.
BROADCAST_CHUNK = 100


def publish_chunked(events: list) -> None:
    for start in range(0, len(events), BROADCAST_CHUNK):
        realtime.publish(events[start : start + BROADCAST_CHUNK])


@router.get("/admissions", response_model=list[Admission])
def list_admissions(
    institution_id: str | None = None,
    programme_id: str | None = None,
    academic_year: str | None = None,
    status: AdmissionStatus | None = None,
    seat_pool: SeatPool | None = None,
    limit: int = Query(50, ge=1, le=service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    user: User = Depends(READERS),
    real: bool = Depends(REAL),
) -> list[dict]:
    """List admissions. APAAR IDs are always masked as XXXX-XXXX-1234."""
    filters = {
        "institution_id": institution_id,
        "programme_id": programme_id,
        "academic_year": academic_year,
        "status": status,
        "seat_pool": seat_pool,
    }
    if real:
        with transaction() as conn:
            return service.list_admissions(conn, user, filters, limit, offset)
    rows = mock("admissions")
    matching = [r for r in rows if all(v is None or r[k] == v for k, v in filters.items())]
    return matching[offset : offset + limit]


@router.post(
    "/admissions/{admission_id}/edit-requests", response_model=EditRequest, status_code=201
)
def create_edit_request(
    admission_id: str,
    body: EditRequestCreate,
    user: User = Depends(EDITORS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
) -> dict:
    """422 INVALID_EDIT_VALUE when new_value fails the upload rules for its field
    (GET /edit-requests/fields lists the fields and allowed values)."""
    if real:
        with transaction() as conn:
            return service.create_edit_request(conn, admission_id, body.model_dump(), user)
    admission = next((a for a in mock("admissions") if a["id"] == admission_id), None)
    if admission is None:
        raise not_found("Admission", admission_id)
    new_value = service.check_edit_value(body.field, body.new_value, settings.admission_cutoff_date)
    request = mock("edit_requests")[0]
    old = admission.get(body.field)
    request.update(
        admission_id=admission_id,
        field=body.field,
        old_value=None if old is None else str(old),
        new_value=new_value,
        reason=body.reason,
        requested_by=user.id,
        created_at=datetime.now(UTC).isoformat(),
    )
    return request


@router.get("/edit-requests/fields", response_model=list[EditableField])
def list_editable_fields(user: User = Depends(READERS)) -> list[dict]:
    """Fields an edit request may change, with their type and, for enum fields, the
    allowed values."""
    return service.editable_fields()


@router.get("/edit-requests", response_model=list[EditRequest])
def list_edit_requests(
    status: EditRequestStatus | None = None,
    institution_id: str | None = None,
    academic_year: str | None = None,
    limit: int = Query(50, ge=1, le=service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    user: User = Depends(READERS),
    real: bool = Depends(REAL),
) -> list[dict]:
    """Edit requests, newest first, with the admission each one changes (APAAR masked).

    aicte_admin and auditor see every institution; institution users only their own.
    """
    filters = {"status": status, "institution_id": institution_id, "academic_year": academic_year}
    if real:
        with transaction() as conn:
            return service.list_edit_requests(conn, user, filters, limit, offset)
    institution = scoped_institution(user, institution_id)
    admissions = {a["id"]: a for a in mock("admissions")}
    out = []
    for request in sorted(mock("edit_requests"), key=lambda r: r["created_at"], reverse=True):
        admission = admissions.get(request["admission_id"])
        if (
            (status and request["status"] != status)
            or (institution and (admission or {}).get("institution_id") != institution)
            or (academic_year and (admission or {}).get("academic_year") != academic_year)
        ):
            continue
        out.append(
            {
                **request,
                "institution_id": admission["institution_id"] if admission else None,
                "admission": admission,
            }
        )
    return out[offset : offset + limit]


@router.post("/edit-requests/{edit_request_id}/decision", response_model=EditRequest)
def decide_edit_request(
    edit_request_id: str,
    body: EditDecision,
    background: BackgroundTasks,
    user: User = Depends(DECIDERS),
    real: bool = Depends(REAL),
) -> dict:
    """Approve (and apply) or reject. Approving a 'withdrawal' request withdraws the
    admission. Broadcasts edit_request.decided."""
    if real:
        with transaction() as conn:
            request, events = service.decide_edit_request(
                conn, edit_request_id, body.decision, body.note, user
            )
        background.add_task(realtime.publish, events)
        return request
    request = next((r for r in mock("edit_requests") if r["id"] == edit_request_id), None)
    if request is None:
        raise not_found("Edit request", edit_request_id)
    request.update(
        status=body.decision,
        decided_by=user.id,
        decision_note=body.note,
        decided_at=datetime.now(UTC).isoformat(),
    )
    return request


@router.post("/admissions/{admission_id}/withdraw", response_model=Admission)
def withdraw_admission(
    admission_id: str,
    body: WithdrawRequest,
    background: BackgroundTasks,
    user: User = Depends(WITHDRAWERS),
    real: bool = Depends(REAL),
) -> dict:
    """Withdraw an admission (reason required) and release its seat in the Seat Ledger.

    After the academic year's submission window closes or is locked this returns 409
    SUBMISSION_WINDOW_CLOSED: file an edit request with field 'withdrawal' instead.
    Broadcasts admission.status_changed.
    """
    if real:
        with transaction() as conn:
            admission, events = service.withdraw(conn, admission_id, body.reason, user)
        background.add_task(realtime.publish, events)
        return admission
    admission = next((a for a in mock("admissions") if a["id"] == admission_id), None)
    if admission is None:
        raise not_found("Admission", admission_id)
    admission["status"] = "withdrawn"
    return admission


@router.post(
    "/admin/admissions/mark-no-response",
    response_model=MarkNoResponseResult,
    tags=["admin"],
)
def mark_no_response(
    body: MarkNoResponseRequest,
    background: BackgroundTasks,
    user: User = Depends(DECIDERS),
    real: bool = Depends(REAL),
) -> dict:
    """Set no_response on submitted admissions committed more than older_than_days ago."""
    if real:
        with transaction() as conn:
            marked, events = student_responses.mark_no_response(
                conn, body.older_than_days, actor=user.id
            )
        background.add_task(publish_chunked, events)
        return {"marked": marked, "older_than_days": body.older_than_days}
    marked = sum(1 for a in mock("admissions") if a["status"] == "submitted")
    return {"marked": marked, "older_than_days": body.older_than_days}
