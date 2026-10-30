# Owner: Dev B
"""Committed admissions and edit requests on Postgres. APAAR IDs always leave masked."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import psycopg
from fastapi import HTTPException, status
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.core.rule_codes import RuleCode
from app.core.security import scoped_institution
from app.models.auth import User
from app.services import audit_store
from app.services import submission_windows as windows
from app.services.batches import Event, as_uuid
from app.services.ingestion import normalize_row
from app.services.validation import (
    ADMISSION_MODES,
    ValidationContext,
    check_row,
    mask_apaar,
)

MAX_LIMIT = 200

_SELECT = """
    select a.id, a.student_id, s.full_name as student_name, s.apaar_id, s.provisional_id,
           s.opted_out, s.dob, p.institution_id, a.programme_id, p.code as programme_code,
           a.academic_year, a.pool::text as seat_pool, a.admission_mode, a.admission_date,
           a.qualifying_exam_pct, a.status::text as status, a.batch_id, a.active
    from public.admissions a
    join public.students s on s.id = a.student_id
    join public.programmes p on p.id = a.programme_id
"""

# Fields an institution may ask to correct, mapped to (table alias, column, cast).
EDITABLE = {
    "admission_date": ("admissions", "admission_date", "date"),
    "admission_mode": ("admissions", "admission_mode", "text"),
    "qualifying_exam_pct": ("admissions", "qualifying_exam_pct", "numeric"),
    "student_name": ("students", "full_name", "text"),
    "dob": ("students", "dob", "date"),
}
# Not a column: approving an edit request for this field withdraws the admission.
WITHDRAWAL = "withdrawal"
# What GET /edit-requests/fields reports for each field: its type and, if enumerated,
# the allowed values.
FIELD_TYPES = {
    "admission_date": "date",
    "admission_mode": "enum",
    "qualifying_exam_pct": "number",
    "student_name": "text",
    "dob": "date",
    WITHDRAWAL: "enum",
}
ALLOWED_VALUES: dict[str, tuple[str, ...]] = {
    "admission_mode": ADMISSION_MODES,
    WITHDRAWAL: ("withdrawn",),
}
INVALID_EDIT_VALUE = "INVALID_EDIT_VALUE"
# Upload warnings that still block an edit request; every upload error blocks one.
_BLOCKING_WARNINGS = {RuleCode.ADMISSION_AFTER_CUTOFF}


def editable_fields() -> list[dict[str, Any]]:
    return [
        {
            "field": name,
            "type": kind,
            "allowed_values": list(ALLOWED_VALUES[name]) if name in ALLOWED_VALUES else None,
        }
        for name, kind in FIELD_TYPES.items()
    ]


def _invalid_edit(field: str, message: str) -> HTTPException:
    detail: dict[str, Any] = {"code": INVALID_EDIT_VALUE, "field": field, "message": message}
    if field in ALLOWED_VALUES:
        detail["allowed_values"] = list(ALLOWED_VALUES[field])
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def check_edit_value(field: str, new_value: str, cutoff: date) -> str:
    """Check new_value with the upload rules for its field; returns it as it will be stored.

    Raises 422 INVALID_EDIT_VALUE so a request that could never be applied is not filed.
    """
    if field not in FIELD_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"field must be one of {sorted(FIELD_TYPES)}"
        )
    if field == WITHDRAWAL:
        if new_value.strip().lower() != "withdrawn":
            raise _invalid_edit(field, "new_value for withdrawal must be 'withdrawn'.")
        return "withdrawn"
    row = normalize_row({field: new_value}, {field: field}, 1, secret="")
    ctx = ValidationContext(cutoff=cutoff, run_engine_hooks=False)
    for finding in check_row(row, ctx):
        if finding.rule_code in _BLOCKING_WARNINGS:
            message = f"{field} must be on or before the admission cut-off {cutoff.isoformat()}."
            raise _invalid_edit(field, message)
        if finding.severity == "error" and finding.evidence.get("field") == field:
            raise _invalid_edit(field, finding.message)
    value = row.values[field]
    return value.isoformat() if isinstance(value, date) else str(value)


def _admission(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "student_id": str(row["student_id"]),
        "student_name": row["student_name"],
        "apaar_id_masked": mask_apaar(row["apaar_id"]),
        "provisional_id": row["provisional_id"],
        "apaar_opt_out": row["opted_out"],
        "institution_id": str(row["institution_id"]),
        "programme_id": str(row["programme_id"]),
        "programme_code": row["programme_code"],
        "academic_year": row["academic_year"],
        "seat_pool": row["seat_pool"],
        "admission_mode": row["admission_mode"],
        "admission_date": row["admission_date"],
        "qualifying_exam_pct": float(row["qualifying_exam_pct"] or 0),
        "status": row["status"],
        "batch_id": str(row["batch_id"]) if row["batch_id"] else None,
    }


def list_admissions(
    conn: psycopg.Connection, user: User, filters: dict[str, Any], limit: int, offset: int
) -> list[dict[str, Any]]:
    institution = scoped_institution(user, filters.get("institution_id"))
    # Withdrawn admissions are inactive; they are listed only when asked for by status.
    clauses = [] if filters.get("status") == "withdrawn" else ["a.active"]
    params: list[Any] = []
    for column, value in (
        ("p.institution_id", institution),
        ("a.programme_id", filters.get("programme_id")),
        ("a.academic_year", filters.get("academic_year")),
        ("a.status::text", filters.get("status")),
        ("a.pool::text", filters.get("seat_pool")),
    ):
        if value is not None:
            if column.endswith("_id") and as_uuid(value) is None:
                return []
            clauses.append(f"{column} = %s")
            params.append(value)
    sql = (
        f"{_SELECT} where {' and '.join(clauses)}"
        " order by a.created_at desc, a.id limit %s offset %s"
    )
    rows = conn.execute(sql, (*params, min(limit, MAX_LIMIT), offset)).fetchall()
    return [_admission(r) for r in rows]


def _load_admission(
    conn: psycopg.Connection, admission_id: str, user: User, lock: bool = False
) -> dict[str, Any]:
    sql = f"{_SELECT} where a.id = %s" + (" for update of a" if lock else "")
    row = conn.execute(sql, (admission_id,)).fetchone() if as_uuid(admission_id) else None
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Admission '{admission_id}' not found")
    scoped_institution(user, str(row["institution_id"]))
    return row


def _edit_request(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "id": str(row["id"]),
        "admission_id": str(row["admission_id"]),
        "requested_by": str(row["requested_by"]) if row["requested_by"] else "demo-user",
        "decided_by": str(row["decided_by"]) if row["decided_by"] else None,
    }


def list_edit_requests(
    conn: psycopg.Connection, user: User, filters: dict[str, Any], limit: int, offset: int
) -> list[dict[str, Any]]:
    """Edit requests newest first, each with its admission (APAAR masked).

    Institution users see only their own institution's requests.
    """
    institution = scoped_institution(user, filters.get("institution_id"))
    if institution is not None and as_uuid(institution) is None:
        return []
    rows = conn.execute(
        """
        select er.*, p.institution_id
        from public.edit_requests er
        join public.admissions a on a.id = er.admission_id
        join public.programmes p on p.id = a.programme_id
        where (%(status)s::text is null or er.status = %(status)s)
          and (%(inst)s::uuid is null or p.institution_id = %(inst)s::uuid)
          and (%(year)s::text is null or a.academic_year = %(year)s)
        order by er.created_at desc, er.id
        limit %(limit)s offset %(offset)s
        """,
        {
            "status": filters.get("status"),
            "inst": institution,
            "year": filters.get("academic_year"),
            "limit": min(limit, MAX_LIMIT),
            "offset": offset,
        },
    ).fetchall()
    if not rows:
        return []
    admissions = {
        str(a["id"]): _admission(a)
        for a in conn.execute(
            f"{_SELECT} where a.id = any(%s::uuid[])",
            ([str(r["admission_id"]) for r in rows],),
        ).fetchall()
    }
    return [
        {
            **_edit_request({k: v for k, v in r.items() if k != "institution_id"}),
            "institution_id": str(r["institution_id"]),
            "admission": admissions.get(str(r["admission_id"])),
        }
        for r in rows
    ]


def create_edit_request(
    conn: psycopg.Connection, admission_id: str, body: dict[str, str], user: User
) -> dict[str, Any]:
    new_value = check_edit_value(
        body["field"], body["new_value"], get_settings().admission_cutoff_date
    )
    admission = _load_admission(conn, admission_id, user)
    if not admission["active"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admission is withdrawn")
    old = admission["status"] if body["field"] == WITHDRAWAL else admission.get(body["field"])
    # requested_by holds the same actor string as the audit event, demo actors included.
    actor = user.id
    row = conn.execute(
        """
        insert into public.edit_requests
          (admission_id, field, old_value, new_value, reason, requested_by)
        values (%s, %s, %s, %s, %s, %s) returning *
        """,
        (
            admission_id,
            body["field"],
            None if old is None else str(old),
            new_value,
            body["reason"],
            actor,
        ),
    ).fetchone()
    audit_store.append_event(
        conn,
        actor,
        "edit_request.created",
        "edit_request",
        row["id"],
        {"admission_id": admission_id, "field": body["field"]},
    )
    return _edit_request(row)


def decide_edit_request(
    conn: psycopg.Connection, edit_request_id: str, decision: str, note: str | None, user: User
) -> tuple[dict[str, Any], list[Event]]:
    """Approve (and apply) or reject a pending edit request. Returns the broadcasts."""
    row = (
        conn.execute(
            "select * from public.edit_requests where id = %s for update", (edit_request_id,)
        ).fetchone()
        if as_uuid(edit_request_id)
        else None
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Edit request '{edit_request_id}' not found"
        )
    if row["status"] != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Edit request is already {row['status']}")
    events: list[Event] = []
    if decision == "approved" and row["field"] == WITHDRAWAL:
        _, events = withdraw(
            conn, str(row["admission_id"]), row["reason"], user, edit_request_id=edit_request_id
        )
    elif decision == "approved":
        table, column, cast = EDITABLE[row["field"]]
        target = (
            "where id = %s"
            if table == "admissions"
            else "where id = (select student_id from public.admissions where id = %s)"
        )
        try:
            conn.execute(
                f"update public.{table} set {column} = %s::{cast} {target}",
                (row["new_value"], row["admission_id"]),
            )
        except psycopg.Error as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "new_value is not valid for this field"
            ) from exc
    # decided_by holds the same actor string as the audit event, demo actors included.
    actor = user.id
    row = conn.execute(
        """
        update public.edit_requests
        set status = %s, decided_by = %s, decision_note = %s, decided_at = now()
        where id = %s returning *
        """,
        (decision, actor, note, edit_request_id),
    ).fetchone()
    audit_store.append_event(
        conn,
        actor,
        f"edit_request.{decision}",
        "edit_request",
        row["id"],
        {"admission_id": str(row["admission_id"]), "field": row["field"]},
    )
    events.append(
        (
            "edit_request.decided",
            {
                "edit_request_id": str(row["id"]),
                "admission_id": str(row["admission_id"]),
                "status": row["status"],
                "decided_at": row["decided_at"].isoformat(),
            },
        )
    )
    return _edit_request(row), events


# ---------------------------------------------------------------------------- status changes
def status_event(
    admission_id: Any, student_id: Any, old: str, new: str, at: datetime | None = None
) -> Event:
    return (
        "admission.status_changed",
        {
            "admission_id": str(admission_id),
            "student_id": str(student_id),
            "from": old,
            "to": new,
            "changed_at": (at or datetime.now(UTC)).isoformat(),
        },
    )


def _note_released_seat(
    conn: psycopg.Connection, user: User, admission: dict[str, Any]
) -> Event | None:
    """If the pool is back within capacity, add a note to its open intake_overrun case."""
    key = (str(admission["programme_id"]), admission["academic_year"], admission["seat_pool"])
    case = conn.execute(
        """
        select id, evidence from public.review_cases
        where kind = 'intake_overrun' and status = 'open' and institution_id = %s
          and evidence->>'programme_id' = %s and evidence->>'academic_year' = %s
          and evidence->>'pool' = %s
        for update
        """,
        (admission["institution_id"], *key),
    ).fetchone()
    if case is None:
        return None
    approved = conn.execute(
        """
        select approved_seats from public.seat_pools
        where programme_id = %s and academic_year = %s and pool = %s::public.seat_pool
        order by rule_version desc limit 1
        """,
        key,
    ).fetchone()
    used = conn.execute(
        """
        select count(*) as n from public.admissions
        where active and programme_id = %s and academic_year = %s and pool = %s::public.seat_pool
        """,
        key,
    ).fetchone()["n"]
    seats = approved["approved_seats"] if approved else 0
    if used > seats:
        return None
    now = datetime.now(UTC)
    text = (
        f"Withdrawal of admission {admission['id']} brought the {key[2]} pool back within"
        f" capacity: {used} admitted against {seats} approved. Case left open for review."
    )
    updated = conn.execute(
        """
        update public.review_cases
        set notes = notes || %s, updated_at = now()
        where id = %s returning id, status::text as status, updated_at
        """,
        (Jsonb([{"at": now.isoformat(), "text": text}]), case["id"]),
    ).fetchone()
    audit_store.append_event(
        conn,
        user.id,
        "review_case.noted",
        "review_case",
        updated["id"],
        {"admission_id": str(admission["id"]), "used": used, "approved": seats},
    )
    return (
        "review_case.updated",
        {
            "case_id": str(updated["id"]),
            "status": updated["status"],
            "updated_at": updated["updated_at"].isoformat(),
        },
    )


def withdraw(
    conn: psycopg.Connection,
    admission_id: str,
    reason: str,
    user: User,
    edit_request_id: str | None = None,
) -> tuple[dict[str, Any], list[Event]]:
    """Withdraw an admission and release its seat in the Seat Ledger.

    After the academic year's window has closed or been locked, only an approved
    ``withdrawal`` edit request (``edit_request_id``) may do this.
    """
    admission = _load_admission(conn, admission_id, user, lock=True)
    if not admission["active"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Admission is already withdrawn")
    if edit_request_id is None:
        locked = windows.changes_locked(conn, admission["academic_year"])
        if locked:
            raise windows.closed_error(
                admission["academic_year"],
                locked,
                "file an edit request with field 'withdrawal' for an aicte_admin to approve.",
            )
    row = conn.execute(
        """
        update public.admissions
        set active = false, status = 'withdrawn', withdrawn_at = now(), withdrawal_reason = %s
        where id = %s returning withdrawn_at
        """,
        (reason, admission_id),
    ).fetchone()
    audit_store.append_event(
        conn,
        user.id,
        "admission.withdrawn",
        "admission",
        admission_id,
        {"from": admission["status"]}
        | ({"edit_request_id": edit_request_id} if edit_request_id else {}),
    )
    events = [
        status_event(
            admission_id,
            admission["student_id"],
            admission["status"],
            "withdrawn",
            row["withdrawn_at"],
        )
    ]
    noted = _note_released_seat(conn, user, admission)
    if noted:
        events.append(noted)
    out = _admission({**admission, "status": "withdrawn"})
    return out, events
