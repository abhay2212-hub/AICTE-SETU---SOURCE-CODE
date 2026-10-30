# Owner: Dev B
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.submission_windows import SubmissionWindow, SubmissionWindowCreate
from app.services import realtime
from app.services import submission_windows as service

router = APIRouter(prefix="/submission-windows", tags=["submission-windows"])

READERS = require_roles("aicte_admin", "auditor", "institution_admin", "institution_operator")
SETTERS = require_roles("aicte_admin")
REAL = source("submission_windows")


def _mock_windows() -> list[dict]:
    return [service.window_out(_parse_times(w)) for w in mock("submission_windows")]


def _parse_times(window: dict) -> dict:
    for key in ("opens_at", "closes_at", "locked_at", "created_at", "updated_at"):
        if isinstance(window.get(key), str):
            window[key] = datetime.fromisoformat(window[key])
    return window


@router.get("", response_model=list[SubmissionWindow])
def list_windows(user: User = Depends(READERS), real: bool = Depends(REAL)) -> list[dict]:
    """Every academic year's window with its current state (not_open, open, closed, locked)."""
    if real:
        with transaction() as conn:
            return service.list_windows(conn)
    return _mock_windows()


@router.post("", response_model=SubmissionWindow, status_code=201)
def set_window(
    body: SubmissionWindowCreate,
    background: BackgroundTasks,
    user: User = Depends(SETTERS),
    real: bool = Depends(REAL),
) -> dict:
    """Create the window for an academic year, or move the dates of an unlocked one.

    A locked window cannot be changed (409 SUBMISSION_WINDOW_CLOSED).
    """
    if real:
        with transaction() as conn:
            window, event = service.upsert_window(conn, body.model_dump(), user)
        background.add_task(realtime.publish, [event])
        return window
    now = datetime.now(UTC)
    window = {
        "id": "a0000000-0000-4000-8000-000000000099",
        **body.model_dump(),
        "locked_at": None,
        "created_at": now,
        "updated_at": now,
    }
    return service.window_out(window)


@router.post("/{window_id}/lock", response_model=SubmissionWindow)
def lock_window(
    window_id: str,
    background: BackgroundTasks,
    user: User = Depends(SETTERS),
    real: bool = Depends(REAL),
) -> dict:
    """Lock the window. From now on admission changes for that year need an approved edit
    request. Locking an already locked window returns it unchanged."""
    if real:
        with transaction() as conn:
            window, event = service.lock_window(conn, window_id, user)
        if event:
            background.add_task(realtime.publish, [event])
        return window
    window = next((w for w in mock("submission_windows") if w["id"] == window_id), None)
    if window is None:
        raise not_found("Submission window", window_id)
    window = _parse_times(window)
    window["locked_at"] = window["locked_at"] or datetime.now(UTC)
    return service.window_out(window)
