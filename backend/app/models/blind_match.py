# Owner: Dev B (contract consumed by Dev A's blind-match router)
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import CaseStatus


class EncodeRequest(BaseModel):
    fields: dict[str, str]


class EncodeResponse(BaseModel):
    demo_only: Literal[True] = True
    bits: int
    k: int
    set_bits: int
    encoding_b64: str


class BlindMatchCase(BaseModel):
    """record_* are student ids. For institution users the other institution's side reads
    'hidden' (record and institution id) with no name."""

    id: str
    record_a: str
    record_b: str
    institution_a_id: str
    institution_b_id: str
    dice: float
    fields_compared: list[str]
    status: CaseStatus
    review_case_id: str | None = None
    institution_a_name: str | None = None
    institution_b_name: str | None = None
    programme_a: str | None = None
    programme_b: str | None = None
    academic_year_a: str | None = None
    academic_year_b: str | None = None
    identity_hint_a: str | None = Field(
        None, description="Initials and birth year; aicte_admin and auditor only"
    )
    identity_hint_b: str | None = None
    created_at: datetime | None = None


class BlindMatchScanResult(BaseModel):
    students_encoded: int
    candidates: int
    matches: int
    cases_created: list[str]
