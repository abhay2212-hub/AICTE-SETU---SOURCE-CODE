# Owner: Dev B
"""Outbound institution webhooks (shared/integration-api.md).

After a commit, batch.committed is POSTed to the institution's webhook_url with
X-Signature: sha256=<HMAC-SHA256 of the raw body>. The per-institution secret is derived
from WEBHOOK_SIGNING_KEY and a stored key id, so the database never holds it. Delivery is
best effort: one attempt, 3-second timeout, failures are logged and never fail the commit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 3.0


def secret_for(signing_key: str, institution_id: str, key_id: str) -> str:
    mac = hmac.new(
        signing_key.encode(), f"outbound-webhook:{institution_id}:{key_id}".encode(), "sha256"
    )
    return "whsec_" + mac.hexdigest()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def body_for(event: str, payload: dict[str, Any]) -> bytes:
    return json.dumps({"event": event, "payload": payload}, separators=(",", ":")).encode()


def deliver(url: str, secret: str, event: str, payload: dict[str, Any]) -> bool:
    """POST one event. Returns True on a 2xx response."""
    body = body_for(event, payload)
    try:
        response = httpx.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Event": event,
                "X-Signature": sign(secret, body),
            },
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("Webhook delivery of %s failed: %s", event, type(exc).__name__)
        return False
