# Owner: Dev B
"""The signed-in student's own records, consents and access log (shared/credentials.md)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.student_responses import StudentPortalResponse, StudentResponseResult
from app.models.students import AccessLogEntry, Consent, ConsentCreate, StudentRecords
from app.services import realtime, student_responses
from app.services import students as service
from app.services.student_responses import RESPONSES
from app.services.validation import mask_apaar

router = APIRouter(prefix="/students/me", tags=["students"])

STUDENT = require_roles("student")
REAL = source("students")
DEMO_STUDENT = Header(
    default=None, description="MOCK_MODE only: act as this student id instead of the demo one"
)


def _fixture_student(student_id: str) -> dict:
    student = mock("students").get(student_id)
    if student is None:
        raise not_found("Student", student_id)
    masked = mask_apaar(student["apaar_id"])
    return {**student, "apaar_id": masked, "apaar_id_masked": masked}


@router.get("/records", response_model=StudentRecords)
def my_records(
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    x_demo_student: str | None = DEMO_STUDENT,
) -> dict:
    """The student's admissions, newest first, with status. APAAR IDs are masked."""
    if real:
        with transaction() as conn:
            return service.records(conn, service.resolve_student_id(conn, user, x_demo_student))
    student_id = service.fixture_student_id(user, x_demo_student)
    admissions = [a for a in mock("admissions") if a["student_id"] == student_id]
    return {"student": _fixture_student(student_id), "admissions": admissions}


@router.post("/admissions/{admission_id}/response", response_model=StudentResponseResult)
def respond(
    admission_id: str,
    body: StudentPortalResponse,
    background: BackgroundTasks,
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    x_demo_student: str | None = DEMO_STUDENT,
) -> dict:
    """Confirm or dispute one of the student's own admissions (channel portal).

    Same rules as POST /internal/student-responses; another student's admission is 404.
    """
    if real:
        with transaction() as conn:
            student_id = service.resolve_student_id(conn, user, x_demo_student)
            service.own_admission(conn, student_id, admission_id)
            result, events = student_responses.apply_response(
                conn, admission_id, body.response, "portal"
            )
        background.add_task(realtime.publish, events)
        return result
    student_id = service.fixture_student_id(user, x_demo_student)
    admission = next(
        (
            a
            for a in mock("admissions")
            if a["id"] == admission_id and a["student_id"] == student_id
        ),
        None,
    )
    if admission is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {"code": "ADMISSION_NOT_FOUND", "message": f"Admission '{admission_id}' not found"},
        )
    target = RESPONSES[body.response]
    return {
        "admission_id": admission_id,
        "status": target,
        "changed": admission["status"] != target,
        "review_case_id": None,
    }


@router.get("/consents", response_model=list[Consent])
def my_consents(
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    x_demo_student: str | None = DEMO_STUDENT,
) -> list[dict]:
    if real:
        with transaction() as conn:
            return service.consents(conn, service.resolve_student_id(conn, user, x_demo_student))
    return mock("consents")


@router.post("/consents", response_model=Consent, status_code=201)
def change_consent(
    body: ConsentCreate,
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    x_demo_student: str | None = DEMO_STUDENT,
) -> dict:
    """Grant (or renew) or withdraw a consent. purpose 'apaar_sharing' is the opt-in to
    sharing the APAAR ID with the SIMULATED APAAR systems; withdrawing it is the opt-out."""
    if real:
        with transaction() as conn:
            student_id = service.resolve_student_id(conn, user, x_demo_student)
            return service.change_consent(conn, student_id, body.model_dump())
    return service.fixture_consent(body.model_dump(), mock("consents"))


@router.get("/access-log", response_model=list[AccessLogEntry])
def my_access_log(
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    x_demo_student: str | None = DEMO_STUDENT,
) -> list[dict]:
    """Who looked at the student's record, newest first."""
    if real:
        with transaction() as conn:
            return service.access_log(conn, service.resolve_student_id(conn, user, x_demo_student))
    return sorted(mock("access_log"), key=lambda e: e["accessed_at"], reverse=True)
