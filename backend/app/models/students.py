# Owner: Dev B (contract: shared/credentials.md sections 10 and 11)
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.admissions import Admission


class StudentProfile(BaseModel):
    id: str
    full_name: str
    apaar_id: str | None = Field(description="Masked as XXXX-XXXX-1234; never the full ID")
    apaar_id_masked: str | None = None
    provisional_id: str | None = None
    opted_out: bool
    dob: date
    telegram_linked: bool


class StudentRecords(BaseModel):
    student: StudentProfile
    admissions: list[Admission]


class ConsentCreate(BaseModel):
    verifier_id: str = Field(min_length=1, max_length=200)
    verifier_name: str | None = Field(None, max_length=200)
    purpose: str = Field(
        min_length=1, max_length=200, description="'apaar_sharing' is the APAAR sharing opt-in"
    )
    fields: list[str] = Field(default_factory=list)
    expires_in_days: int = Field(30, ge=1, le=365)
    action: Literal["grant", "withdraw"] | None = Field(None, description="Default grant")


class Consent(BaseModel):
    id: str
    verifier_id: str
    verifier_name: str
    purpose: str
    fields: list[str]
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None


class AccessLogEntry(BaseModel):
    id: str
    accessor: str
    accessor_role: str
    purpose: str
    fields: list[str]
    consent_id: str | None
    accessed_at: datetime
