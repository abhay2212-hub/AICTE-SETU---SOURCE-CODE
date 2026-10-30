# Owner: Dev B
"""Review cases raised by the Seat Ledger, validation, Blind Match, disputes and signals."""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import HTTPException, status

from app.core.security import scoped_institution
from app.models.auth import User
from app.services import audit_store
from app.services.batches import Event, as_uuid

_COLUMNS = (
    "id, kind, institution_id, title, evidence, status::text as status, reviewer_note,"
    " created_at, updated_at, resolved_at"
)


def _case(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "id": str(row["id"]), "institution_id": str(row["institution_id"])}


def list_cases(
    conn: psycopg.Connection, user: User, kind: str | None, case_status: str | None
) -> list[dict[str, Any]]:
    institution = scoped_institution(user)
    rows = conn.execute(
        f"""
        select {_COLUMNS} from public.review_cases
        where (%(kind)s::text is null or kind = %(kind)s)
          and (%(status)s::text is null or status::text = %(status)s)
          and (%(inst)s::uuid is null or institution_id = %(inst)s::uuid)
        order by created_at desc
        """,
        {"kind": kind, "status": case_status, "inst": institution},
    ).fetchall()
    return [_case(r) for r in rows]


def get_case(
    conn: psycopg.Connection, case_id: str, user: User, lock: bool = False
) -> dict[str, Any]:
    row = (
        conn.execute(
            f"select {_COLUMNS} from public.review_cases where id = %s"
            + (" for update" if lock else ""),
            (case_id,),
        ).fetchone()
        if as_uuid(case_id)
        else None
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Review case '{case_id}' not found")
    scoped_institution(user, str(row["institution_id"]))
    return _case(row)


def resolve_case(
    conn: psycopg.Connection, case_id: str, outcome: str, note: str, user: User
) -> tuple[dict[str, Any], Event]:
    get_case(conn, case_id, user, lock=True)
    row = conn.execute(
        f"""
        update public.review_cases
        set status = %s::public.case_status, reviewer_note = %s, reviewer_id = %s,
            updated_at = now(),
            resolved_at = case when %s in ('confirmed', 'dismissed') then now() end
        where id = %s returning {_COLUMNS}
        """,
        (outcome, note, as_uuid(user.id), outcome, case_id),
    ).fetchone()
    audit_store.append_event(
        conn, user.id, "review_case.updated", "review_case", case_id, {"status": outcome}
    )
    event = (
        "review_case.updated",
        {
            "case_id": str(row["id"]),
            "status": row["status"],
            "updated_at": row["updated_at"].isoformat(),
        },
    )
    return _case(row), event
