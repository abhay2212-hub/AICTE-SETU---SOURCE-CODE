# Owner: Dev B
"""Simulated government-system integrations. Every response carries simulated=true."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.models.auth import Role, User


class SsoMockRequest(BaseModel):
    role: Role = "institution_admin"
    institution_id: str | None = None
    email: str | None = None


class SsoMockResponse(BaseModel):
    simulated: Literal[True] = True
    source: str = "SIMULATED AICTE portal SSO"
    user: User
    demo_headers: dict[str, str]


class ApaarVerifyRequest(BaseModel):
    apaar_id: str | None = None
    opted_out: bool = False


class ApaarVerifyResponse(BaseModel):
    simulated: Literal[True] = True
    source: str = "SIMULATED APAAR registry"
    apaar_id_masked: str | None
    result: Literal["found", "not_found", "invalid_format", "opted_out", "missing"]
    rule_code: str | None = None
