# Owner: Dev B
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Programme(BaseModel):
    id: str
    code: str
    name: str
    level: str
    duration_years: int


class Institution(BaseModel):
    id: str
    aicte_code: str
    name: str
    state: str
    parent_trust: str | None = None
    integrity_score: float | None = None


class InstitutionDetail(Institution):
    programmes: list[Programme]


class ApiKeyCreated(BaseModel):
    key_id: str
    institution_id: str
    api_key: str
    created_at: datetime
    note: str = "Shown once. Only a hash is stored."


class ApiKeyRevoked(BaseModel):
    key_id: str
    institution_id: str
    revoked_at: datetime


class WebhookConfigRequest(BaseModel):
    url: str | None = Field(
        None,
        pattern=r"^https?://\S+$",
        description="Receives batch.committed; null removes the webhook",
    )


class WebhookConfig(BaseModel):
    institution_id: str
    webhook_url: str | None = None
    secret: str | None = Field(
        None, description="HMAC-SHA256 signing secret for X-Signature. Shown once."
    )
    note: str = "The secret is shown once; setting the URL again rotates it."
