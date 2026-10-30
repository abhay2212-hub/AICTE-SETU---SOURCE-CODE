# Owner: Dev B
from __future__ import annotations

from pydantic import BaseModel


class PublicStats(BaseModel):
    """Platform-wide aggregates for the landing page. Counts only, no names or IDs."""

    institutions: int
    active_admissions: int
    open_review_cases: int
    audit_chain_ok: bool
    audit_events: int
    academic_year: str
