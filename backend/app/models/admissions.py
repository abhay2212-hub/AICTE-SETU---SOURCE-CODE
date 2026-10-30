# Owner: Dev B
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import AdmissionMode, AdmissionStatus, SeatPool


class Admission(BaseModel):
    id: str
    student_id: str
    student_name: str
    apaar_id_masked: str | None = Field(None, description="Masked as XXXX-XXXX-1234")
    provisional_id: str | None = None
    apaar_opt_out: bool = False
    institution_id: str
    programme_id: str
    programme_code: str
    academic_year: str
    seat_pool: SeatPool
    admission_mode: AdmissionMode
    admission_date: date
    qualifying_exam_pct: float
    status: AdmissionStatus
    batch_id: str | None = None


class EditRequestCreate(BaseModel):
    field: str = Field(
        description="admission_date, admission_mode, qualifying_exam_pct, student_name, dob,"
        " or withdrawal (new_value 'withdrawn'; approving it withdraws the admission)"
    )
    new_value: str
    reason: str = Field(min_length=1)


class EditRequest(BaseModel):
    id: str
    admission_id: str
    field: str
    old_value: str | None = None
    new_value: str
    reason: str
    status: Literal["pending", "approved", "rejected"]
    requested_by: str
    decided_by: str | None = None
    decision_note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    institution_id: str | None = None
    admission: Admission | None = Field(
        None, description="The admission it changes (APAAR masked); set by GET /edit-requests"
    )


EditRequestStatus = Literal["pending", "approved", "rejected"]


class EditableField(BaseModel):
    field: str
    type: Literal["date", "enum", "number", "text"]
    allowed_values: list[str] | None = Field(
        None, description="The only values accepted as new_value; set for enum fields"
    )


class EditDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


class WithdrawRequest(BaseModel):
    reason: str = Field(min_length=1)
