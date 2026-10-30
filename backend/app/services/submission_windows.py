# Owner: Dev B
"""Submission windows: AICTE sets, per academic year, when uploads and commits are allowed.

Uploads and commits for a year need its window to be open. After closes_at or locked_at,
any change to an admission of that year goes through an edit request an aicte_admin
decides. A year without a window row is not restricted.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi import HTTPException, status

from app.models.auth import User
from app.services import audit_store

# batches imports this module, so the two small helpers are local rather than imported.
Event = tuple[str, dict[str, Any]]

WINDOW_CLOSED = "SUBMISSION_WINDOW_CLOSED"

_COLUMNS = "id, academic_year, opens_at, closes_at, locked_at, created_at, updated_at"


def as_uuid(value: str | None) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError):
        return None


def state(row: dict[str, Any], now: datetime | None = None) -> str:
    """not_open, open, closed or locked."""
    now = now or datetime.now(UTC)
    if row.get("locked_at") is not None:
        return "locked"
    if now < row["opens_at"]:
        return "not_open"
    if now >= row["closes_at"]:
        return "closed"
    return "open"


def window_out(row: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    return {**row, "id": str(row["id"]), "state": state(row, now)}


def window_event(row: dict[str, Any]) -> Event:
    return (
        "submission_window.updated",
        {
            "window_id": str(row["id"]),
            "academic_year": row["academic_year"],
            "state": state(row),
            "updated_at": row["updated_at"].isoformat(),
        },
    )


def closed_error(academic_year: str, window_state: str, action: str) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "code": WINDOW_CLOSED,
            "academic_year": academic_year,
            "state": window_state,
            "message": f"The {academic_year} submission window is {window_state.replace('_', ' ')};"
            f" {action}",
        },
    )


def list_windows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"select {_COLUMNS} from public.submission_windows order by academic_year desc"
    ).fetchall()
    return [window_out(r) for r in rows]


def _windows(conn: psycopg.Connection, years: Iterable[str]) -> list[dict[str, Any]]:
    years = sorted(set(years))
    if not years:
        return []
    return conn.execute(
        f"select {_COLUMNS} from public.submission_windows where academic_year = any(%s)",
        (years,),
    ).fetchall()


def ensure_open(conn: psycopg.Connection, years: Iterable[str]) -> None:
    """409 SUBMISSION_WINDOW_CLOSED unless every year with a window has it open."""
    for row in _windows(conn, years):
        current = state(row)
        if current != "open":
            raise closed_error(
                row["academic_year"], current, "uploads and commits are not accepted."
            )


def changes_locked(conn: psycopg.Connection, academic_year: str) -> str | None:
    """The window state when admission changes need an approved edit request, else None."""
    for row in _windows(conn, [academic_year]):
        current = state(row)
        if current in ("closed", "locked"):
            return current
    return None


def upsert_window(
    conn: psycopg.Connection,
    body: dict[str, Any],
    user: User,
    unlock: bool = False,
) -> tuple[dict[str, Any], Event]:
    """Create the window for an academic year, or move the dates of an unlocked one.

    ``unlock`` is for the demo loader only; the API never clears a lock.
    """
    if body["closes_at"] <= body["opens_at"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "closes_at must be after opens_at"
        )
    existing = conn.execute(
        "select id, locked_at from public.submission_windows where academic_year = %s for update",
        (body["academic_year"],),
    ).fetchone()
    if existing and existing["locked_at"] is not None and not unlock:
        raise closed_error(body["academic_year"], "locked", "a locked window cannot be changed.")
    row = conn.execute(
        f"""
        insert into public.submission_windows (academic_year, opens_at, closes_at, created_by)
        values (%s, %s, %s, %s)
        on conflict (academic_year) do update
          set opens_at = excluded.opens_at, closes_at = excluded.closes_at,
              locked_at = null, locked_by = null, updated_at = now()
        returning {_COLUMNS}
        """,
        (body["academic_year"], body["opens_at"], body["closes_at"], as_uuid(user.id)),
    ).fetchone()
    audit_store.append_event(
        conn,
        user.id,
        "submission_window.updated" if existing else "submission_window.created",
        "submission_window",
        row["id"],
        {
            "academic_year": row["academic_year"],
            "opens_at": row["opens_at"].isoformat(),
            "closes_at": row["closes_at"].isoformat(),
        },
    )
    return window_out(row), window_event(row)


def lock_window(
    conn: psycopg.Connection, window_id: str, user: User
) -> tuple[dict[str, Any], Event | None]:
    """Lock a window. Locking twice keeps the first lock time and broadcasts nothing."""
    row = (
        conn.execute(
            f"select {_COLUMNS} from public.submission_windows where id = %s for update",
            (window_id,),
        ).fetchone()
        if as_uuid(window_id)
        else None
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Submission window '{window_id}' not found")
    if row["locked_at"] is not None:
        return window_out(row), None
    row = conn.execute(
        f"""
        update public.submission_windows
        set locked_at = now(), locked_by = %s, updated_at = now()
        where id = %s returning {_COLUMNS}
        """,
        (as_uuid(user.id), window_id),
    ).fetchone()
    audit_store.append_event(
        conn,
        user.id,
        "submission_window.locked",
        "submission_window",
        row["id"],
        {"academic_year": row["academic_year"]},
    )
    return window_out(row), window_event(row)
