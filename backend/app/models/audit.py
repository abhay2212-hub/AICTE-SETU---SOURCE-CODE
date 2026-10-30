# Owner: Dev B
from __future__ import annotations

from pydantic import BaseModel


class AuditVerifyResult(BaseModel):
    ok: bool
    first_broken_index: int | None
    checked: int
