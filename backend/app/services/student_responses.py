# Owner: Dev B
"""Student confirm / dispute of an admission record (shared/student-responses.md).

Dev E's Telegram webhook and student portal call these through POST
/internal/student-responses. Repeating the same response changes nothing.
"""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from app.services import audit_store
from app.services.admissions import status_event
from app.services.batches import Event, as_uuid, case_created_event

RESPONSES = {"confirmed": "student_confirmed", "disputed": "student_disputed"}
CHANNELS = ("telegram", "portal")


def _open_dispute(conn: psycopg.Connection, admission_id: str) -> str | None:
    row = conn.execute(
        "select id from public.review_cases where kind = 'dispute' and status = 'open'"
        " and evidence->>'admission_id' = %s",
        (admission_id,),
    ).fetchone()
    return str(row["id"]) if row else None


def apply_response(
    conn: psycopg.Connection, admission_id: str, response: str, channel: str
) -> tuple[dict[str, Any], list[Event]]:
    """Record a student's response inside the caller's transaction.

    ``confirmed`` sets student_confirmed. ``disputed`` sets student_disputed and opens a
    dispute review case (one open case per admission). Both write an audit event and return
    the admission.status_changed broadcast. The same response twice is a no-op.
    """
    if response not in RESPONSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"response must be one of {sorted(RESPONSES)}"
        )
    if channel not in CHANNELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"channel must be one of {list(CHANNELS)}"
        )
    row = (
        conn.execute(
            """
            select a.id, a.student_id, a.status::text as status, a.active, a.academic_year,
                   p.institution_id, p.code as programme
            from public.admissions a
            join public.programmes p on p.id = a.programme_id
            where a.id = %s
            for update of a
            """,
            (admission_id,),
        ).fetchone()
        if as_uuid(admission_id)
        else None
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {"code": "ADMISSION_NOT_FOUND", "message": f"Admission '{admission_id}' not found"},
        )
    if not row["active"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"code": "ADMISSION_WITHDRAWN", "message": "Admission is withdrawn"},
        )
    admission_id = str(row["id"])
    target = RESPONSES[response]
    if row["status"] == target:
        result = {
            "admission_id": admission_id,
            "status": target,
            "changed": False,
            "review_case_id": _open_dispute(conn, admission_id),
        }
        return result, []

    updated = conn.execute(
        """
        update public.admissions
        set status = %s::public.admission_status, responded_at = now(), response_channel = %s
        where id = %s returning responded_at
        """,
        (target, channel, admission_id),
    ).fetchone()
    actor = f"student:{row['student_id']}"
    audit_store.append_event(
        conn,
        actor,
        "admission.student_response",
        "admission",
        admission_id,
        {"from": row["status"], "to": target, "channel": channel},
    )
    events = [
        status_event(
            admission_id, row["student_id"], row["status"], target, updated["responded_at"]
        )
    ]
    case_id = _open_dispute(conn, admission_id)
    if response == "disputed" and case_id is None:
        evidence = {
            "admission_id": admission_id,
            "institution_id": str(row["institution_id"]),
            "programme": row["programme"],
            "academic_year": row["academic_year"],
            "channel": channel,
        }
        case = conn.execute(
            """
            insert into public.review_cases (kind, institution_id, title, evidence)
            values ('dispute', %s, 'Student disputes admission record', %s)
            returning id, kind, institution_id, status::text as status, created_at
            """,
            (row["institution_id"], Jsonb(evidence)),
        ).fetchone()
        case_id = str(case["id"])
        audit_store.append_event(
            conn,
            actor,
            "review_case.created",
            "review_case",
            case_id,
            {"kind": "dispute", "admission_id": admission_id, "channel": channel},
        )
        events.append(case_created_event(case))
    result = {
        "admission_id": admission_id,
        "status": target,
        "changed": True,
        "review_case_id": case_id,
    }
    return result, events


def mark_no_response(
    conn: psycopg.Connection, older_than_days: int, actor: str = "system"
) -> tuple[int, list[Event]]:
    """Set no_response on active, still-submitted admissions committed more than N days ago."""
    rows = conn.execute(
        """
        update public.admissions
        set status = 'no_response'
        where active and status = 'submitted'
          and created_at < now() - make_interval(days => %s)
        returning id, student_id
        """,
        (older_than_days,),
    ).fetchall()
    if not rows:
        return 0, []
    audit_store.append_event(
        conn,
        actor,
        "admission.no_response_marked",
        "admission",
        None,
        {
            "count": len(rows),
            "older_than_days": older_than_days,
            "admission_ids": sorted(str(r["id"]) for r in rows),
        },
    )
    events = [status_event(r["id"], r["student_id"], "submitted", "no_response") for r in rows]
    return len(rows), events
