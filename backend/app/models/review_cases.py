# Owner: Dev B
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.common import CaseKind, CaseStatus


class ReviewCase(BaseModel):
    id: str
    kind: CaseKind
    institution_id: str
    title: str
    evidence: dict[str, Any]
    status: CaseStatus
    reviewer_note: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None


class ResolveRequest(BaseModel):
    status: Literal["confirmed", "dismissed", "correction_requested"]
    note: str = Field(min_length=1)
