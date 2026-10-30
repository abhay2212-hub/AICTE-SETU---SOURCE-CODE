# Owner: Dev B
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Role = Literal[
    "institution_admin", "institution_operator", "aicte_admin", "student", "verifier", "auditor"
]


class User(BaseModel):
    id: str
    role: Role
    institution_id: str | None = None
    display_name: str | None = None
    demo: bool = False
    # Students only: the students.id this account is, from app_metadata.student_id.
    student_id: str | None = None
