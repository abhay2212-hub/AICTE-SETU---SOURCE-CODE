# Owner: Dev B
"""Hash-chain helpers for the tamper-evident audit log.

Each event stores ``prev_hash`` (the previous event's ``hash``, or GENESIS for the first
event) and ``hash = sha256(prev_hash + canonical(body))``, where the body is every field
except ``prev_hash`` and ``hash``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

GENESIS = "0" * 64

_CHAIN_FIELDS = ("prev_hash", "hash")


def canonical(event: dict) -> str:
    """Deterministic JSON: sorted keys, compact separators, non-ASCII kept as UTF-8."""
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_hash(prev_hash: str, event: dict) -> str:
    """SHA-256 hex digest of ``prev_hash`` followed by the canonical event."""
    return hashlib.sha256((prev_hash + canonical(event)).encode("utf-8")).hexdigest()


def _body(event: dict) -> dict[str, Any]:
    return {k: v for k, v in event.items() if k not in _CHAIN_FIELDS}


def append_event(prev_hash: str, event: dict) -> dict:
    """Return a copy of ``event`` with ``prev_hash`` and ``hash`` set."""
    body = _body(event)
    return {**body, "prev_hash": prev_hash, "hash": compute_hash(prev_hash, body)}


def verify_chain(events: list[dict]) -> int | None:
    """Return the index of the first broken link, or None if the chain is intact."""
    expected_prev = GENESIS
    for index, event in enumerate(events):
        prev_hash = event.get("prev_hash")
        if prev_hash != expected_prev:
            return index
        if compute_hash(prev_hash, _body(event)) != event.get("hash"):
            return index
        expected_prev = event["hash"]
    return None
