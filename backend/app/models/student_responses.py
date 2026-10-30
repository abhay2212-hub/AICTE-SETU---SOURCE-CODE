# Owner: Dev B
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import AdmissionStatus

StudentResponse = Literal["confirmed", "disputed"]
ResponseChannel = Literal["telegram", "portal"]


class StudentResponseRequest(BaseModel):
    admission_id: str
    response: StudentResponse
    channel: ResponseChannel


class StudentPortalResponse(BaseModel):
    """Body of POST /students/me/admissions/{id}/response (channel is always portal)."""

    response: StudentResponse


class StudentResponseResult(BaseModel):
    admission_id: str
    status: AdmissionStatus
    changed: bool = Field(description="False when the same response was already recorded")
    review_case_id: str | None = Field(
        None, description="The open dispute case for this admission, when there is one"
    )


class MarkNoResponseRequest(BaseModel):
    older_than_days: int = Field(14, ge=0, le=365)


class MarkNoResponseResult(BaseModel):
    marked: int
    older_than_days: int
