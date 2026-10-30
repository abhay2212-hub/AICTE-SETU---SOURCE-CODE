# Owner: Dev B
"""Audit log persistence on top of app.core.audit.

Hashed body of each event: actor, action, entity_type, entity_id, payload and created_at
(ISO 8601 UTC with microseconds). The bigserial id only orders the chain. Payloads never
contain raw contacts or full APAAR IDs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.audit import GENESIS, verify_chain
from app.core.audit import append_event as chain_event

# Fixed key for pg_advisory_xact_lock so appends are serialised across connections.
AUDIT_LOCK_KEY = 7_264_660_001


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _body(row: dict[str, Any]) -> dict[str, Any]:
    created = row["created_at"]
    return {
        "actor": row["actor"],
        "action": row["action"],
        "entity_type": row["entity_type"],
        "entity_id": row["entity_id"],
        "payload": row["payload"],
        "created_at": _iso(created) if isinstance(created, datetime) else created,
    }


def append_event(
    conn: psycopg.Connection,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Chain and insert one event inside the caller's transaction."""
    conn.execute("select pg_advisory_xact_lock(%s)", (AUDIT_LOCK_KEY,))
    last = conn.execute("select hash from public.audit_events order by id desc limit 1").fetchone()
    prev_hash = last["hash"] if last else GENESIS
    body = {
        "actor": actor,
        "action": action,
        "entity_type": entity_type,
        "entity_id": None if entity_id is None else str(entity_id),
        "payload": payload,
        "created_at": _iso(datetime.now(UTC)),
    }
    event = chain_event(prev_hash, body)
    conn.execute(
        """
        insert into public.audit_events
          (actor, action, entity_type, entity_id, payload, prev_hash, hash, created_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            event["actor"],
            event["action"],
            event["entity_type"],
            event["entity_id"],
            Jsonb(event["payload"]),
            event["prev_hash"],
            event["hash"],
            event["created_at"],
        ),
    )
    return event


def load_chain(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select id, actor, action, entity_type, entity_id, payload, prev_hash, hash, created_at"
        " from public.audit_events order by id"
    ).fetchall()
    return [{**_body(r), "prev_hash": r["prev_hash"], "hash": r["hash"]} for r in rows]


def verify(conn: psycopg.Connection) -> dict[str, Any]:
    events = load_chain(conn)
    broken = verify_chain(events)
    return {"ok": broken is None, "first_broken_index": broken, "checked": len(events)}
