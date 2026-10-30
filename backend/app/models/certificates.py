# Owner: Dev B (contract for the certificates router)
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Certificate(BaseModel):
    certificate_no: str = Field(description="Certificate ID, equal to its credential ID")
    student_id: str
    apaar_id: str | None = Field(description="Masked XXXX-XXXX-1234; null when opted out")
    provisional_id: str | None = None
    student_name: str
    institution_name: str
    programme_name: str
    academic_year: str
    issued_at: datetime
    verify_url: str
    qr_text: str | None = Field(
        None, description="The QR content: a credential with audience enrolment-certificate"
    )
    expires_at: datetime | None = None
