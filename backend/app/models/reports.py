# Owner: Dev B (contract consumed by Dev C's reports router)
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

GroupBy = Literal["state", "programme", "category", "gender"]


class EnrolmentRow(BaseModel):
    group: str
    admissions: int
    opted_out: int


class EnrolmentReport(BaseModel):
    academic_year: str
    group_by: GroupBy
    total: int
    rows: list[EnrolmentRow]


class AccreditationProgramme(BaseModel):
    programme_code: str
    approved_total: int
    admitted_total: int
    overrun: int


class AccreditationReport(BaseModel):
    institution_id: str
    institution_name: str
    academic_year: str
    integrity_score: float | None
    # Set when integrity_score is null, e.g. "Integrity score not yet computed for 2026-27".
    integrity_note: str | None = None
    apaar_coverage_pct: float
    open_review_cases: int
    programmes: list[AccreditationProgramme]


class StateInstitution(BaseModel):
    institution_id: str
    name: str
    aicte_code: str
    integrity_score: float | None
    open_review_cases: int
    overrun: bool


class StateRow(BaseModel):
    state: str
    institutions: int
    active_admissions: int
    approved_seats: int
    # Admissions / approved seats (1.0 = full); null when the state has no approved seats.
    utilisation: float | None
    overrun_programmes: int
    open_review_cases: int
    avg_integrity_score: float | None
    institutions_list: list[StateInstitution]


class StateTotals(BaseModel):
    institutions: int
    active_admissions: int
    approved_seats: int
    overrun_programmes: int
    open_review_cases: int
    states: int


class StateReport(BaseModel):
    academic_year: str
    totals: StateTotals
    rows: list[StateRow]
