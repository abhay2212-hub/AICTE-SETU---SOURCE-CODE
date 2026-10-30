# Owner: Dev B
"""Service-to-service endpoints for Dev E's Telegram webhook and student portal.

Protected by X-Internal-Token (INTERNAL_API_TOKEN, falling back to TELEGRAM_WEBHOOK_SECRET),
not by user auth. Contract: shared/student-responses.md.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings
from app.core.datasource import source
from app.core.db import transaction
from app.mocks import mock
from app.models.student_responses import StudentResponseRequest, StudentResponseResult
from app.services import realtime, student_responses
from app.services.student_responses import RESPONSES

router = APIRouter(prefix="/internal", tags=["internal"])


def require_internal_token(
    x_internal_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = settings.internal_token
    if not expected:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"code": "INTERNAL_TOKEN_UNCONFIGURED", "message": "INTERNAL_API_TOKEN is not set"},
        )
    if not x_internal_token or not hmac.compare_digest(
        x_internal_token.encode(), expected.encode()
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            {"code": "INVALID_INTERNAL_TOKEN", "message": "Missing or wrong X-Internal-Token"},
        )


@router.post(
    "/student-responses",
    response_model=StudentResponseResult,
    dependencies=[Depends(require_internal_token)],
)
def record_student_response(
    body: StudentResponseRequest,
    background: BackgroundTasks,
    real: bool = Depends(source("admissions")),
) -> dict:
    """Record a student's confirm or dispute of an admission. Idempotent: the same response
    again returns changed=false and broadcasts nothing."""
    if real:
        with transaction() as conn:
            result, events = student_responses.apply_response(
                conn, body.admission_id, body.response, body.channel
            )
        background.add_task(realtime.publish, events)
        return result
    admission = next((a for a in mock("admissions") if a["id"] == body.admission_id), None)
    if admission is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {
                "code": "ADMISSION_NOT_FOUND",
                "message": f"Admission '{body.admission_id}' not found",
            },
        )
    target = RESPONSES[body.response]
    disputes = [
        c["id"]
        for c in mock("review_cases")
        if c["kind"] == "dispute" and c["evidence"].get("admission_id") == body.admission_id
    ]
    return {
        "admission_id": body.admission_id,
        "status": target,
        "changed": admission["status"] != target,
        "review_case_id": disputes[0] if disputes else None,
    }
