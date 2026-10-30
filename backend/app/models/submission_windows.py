# Owner: Dev B
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

WindowState = Literal["not_open", "open", "closed", "locked"]


class SubmissionWindow(BaseModel):
    id: str
    academic_year: str
    opens_at: datetime
    closes_at: datetime
    locked_at: datetime | None = None
    state: WindowState = Field(
        description="not_open before opens_at, open until closes_at, then closed; locked once"
        " an aicte_admin locks it"
    )
    created_at: datetime
    updated_at: datetime


class SubmissionWindowCreate(BaseModel):
    academic_year: str = Field(pattern=r"^\d{4}-\d{2}$", examples=["2026-27"])
    opens_at: datetime
    closes_at: datetime
