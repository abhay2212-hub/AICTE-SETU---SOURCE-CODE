# Owner: Dev B (contract consumed by Dev E's webhooks router)
from __future__ import annotations

from pydantic import BaseModel


class WebhookAck(BaseModel):
    ok: bool
    handled: str | None = None
