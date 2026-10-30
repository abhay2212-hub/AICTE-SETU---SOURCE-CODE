# Owner: Dev B
"""Best-effort broadcasts to the Supabase Realtime channel `platform` (shared/events.md).

Uses the Realtime REST broadcast endpoint, POST {SUPABASE_URL}/realtime/v1/api/broadcast,
with the service role key. Payloads carry IDs, counts and statuses only. Failures are logged
and never fail the API request.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

CHANNEL = "platform"
TIMEOUT_SECONDS = 2.0


def publish(events: list[tuple[str, dict[str, Any]]]) -> bool:
    """Send ``[(event_name, payload), ...]`` in one request. Returns True on success."""
    settings = get_settings()
    if not events:
        return True
    if not settings.supabase_url or not settings.supabase_service_role_key:
        log.info("Realtime not configured; skipped %d event(s)", len(events))
        return False
    key = settings.supabase_service_role_key
    body = {
        "messages": [
            {"topic": CHANNEL, "event": name, "payload": payload} for name, payload in events
        ]
    }
    try:
        response = httpx.post(
            f"{settings.supabase_url.rstrip('/')}/realtime/v1/api/broadcast",
            json=body,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("Realtime broadcast failed for %s: %s", [n for n, _ in events], exc)
        return False
