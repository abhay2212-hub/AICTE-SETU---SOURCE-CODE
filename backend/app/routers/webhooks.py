# Owner: Dev E
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import Settings, get_settings
from app.mocks import require_mock
from app.models.webhooks import WebhookAck

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/telegram", response_model=WebhookAck)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> WebhookAck:
    """Telegram updates. Rejected unless the secret header matches TELEGRAM_WEBHOOK_SECRET."""
    expected = settings.telegram_webhook_secret
    if not expected:
        raise HTTPException(503, "TELEGRAM_WEBHOOK_SECRET is not configured")
    if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
        x_telegram_bot_api_secret_token, expected
    ):
        raise HTTPException(401, "Invalid webhook secret")
    require_mock()
    update = await request.json()
    text = (update.get("message") or {}).get("text", "")
    return WebhookAck(ok=True, handled="start" if text.startswith("/start") else None)
