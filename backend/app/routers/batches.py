# Owner: Dev B
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile

from app.core.api_key_auth import api_key_or_roles
from app.core.config import Settings, get_settings
from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.batches import (
    Batch,
    BatchList,
    BatchUploadResult,
    CommitResult,
    MappingRequest,
    ValidationIssue,
)
from app.models.common import BatchStatus
from app.services import batches as service
from app.services import blind_match, institutions, outbound_webhooks, realtime
from app.services.ingestion import file_sha256, parse_upload, suggest_mapping

router = APIRouter(prefix="/batches", tags=["batches"])

UPLOADERS = require_roles("institution_admin", "institution_operator")
# Upload and commit also accept an institution's X-API-Key (system-to-system integration).
INTEGRATORS = api_key_or_roles("institution_admin", "institution_operator")
READERS = require_roles("institution_admin", "institution_operator", "aicte_admin", "auditor")
REAL = source("batches")


def _mock_batch(batch_id: str) -> dict:
    batch = mock("batch")
    if batch["id"] != batch_id:
        raise not_found("Batch", batch_id)
    return batch


def _fixture_batches() -> list[dict]:
    return [mock("batch")]


def _fixture_years() -> dict[str, set[str]]:
    """Academic years each fixture batch covers, read from the admissions it committed."""
    years: dict[str, set[str]] = {}
    for admission in mock("admissions"):
        if admission.get("batch_id"):
            years.setdefault(admission["batch_id"], set()).add(admission["academic_year"])
    return years


@router.get("", response_model=BatchList)
def list_batches(
    status: BatchStatus | None = None,
    academic_year: str | None = None,
    parent_batch_id: str | None = Query(
        None, description="List the correction batches of this batch"
    ),
    institution_id: str | None = Query(
        None, description="aicte_admin and auditor only; ignored for institution users"
    ),
    limit: int = Query(50, ge=1, le=service.MAX_LIMIT),
    offset: int = Query(0, ge=0),
    user: User = Depends(READERS),
    real: bool = Depends(REAL),
) -> dict:
    """Batch history, newest first.

    Institution users see only their own institution's batches; aicte_admin and auditor
    see every institution and may filter by institution_id.
    """
    filters = {
        "status": status,
        "academic_year": academic_year,
        "parent_batch_id": parent_batch_id,
        "institution_id": institution_id,
    }
    if real:
        with transaction() as conn:
            return service.list_batches(conn, user, filters, limit, offset)
    institution = service.list_scope(user, institution_id)
    years = _fixture_years()
    matching = [
        b
        for b in _fixture_batches()
        if (institution is None or b["institution_id"] == institution)
        and (status is None or b["status"] == status)
        and (parent_batch_id is None or b.get("parent_batch_id") == parent_batch_id)
        and (academic_year is None or academic_year in years.get(b["id"], set()))
    ]
    matching.sort(key=lambda b: (b["created_at"], b["id"]), reverse=True)
    return {
        "items": matching[offset : offset + limit],
        "total": len(matching),
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "",
    response_model=BatchUploadResult,
    status_code=201,
    responses={200: {"description": "Same file already uploaded; existing batch returned"}},
)
async def upload_batch(
    response: Response,
    file: UploadFile = File(...),
    user: User = Depends(INTEGRATORS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Upload a CSV or XLSX of admissions; returns the batch and a suggested column mapping.

    Re-uploading the same file for the same institution returns the existing batch with
    HTTP 200 and duplicate_upload=true. 409 SUBMISSION_WINDOW_CLOSED when the file names an
    academic year whose submission window is not open. Accepts X-API-Key instead of user auth.
    """
    name = file.filename or "upload.csv"
    content = await file.read()
    if real:
        with transaction() as conn:
            result, duplicate = service.upload(conn, user, name, content, settings)
        if duplicate:
            response.status_code = 200
        return result
    parsed = parse_upload(
        name, content, max_mb=settings.max_upload_mb, max_rows=settings.max_upload_rows
    )
    suggestion = suggest_mapping(parsed.headers)
    batch = mock("batch")
    batch.update(
        file_name=name, file_hash=file_sha256(content), status="uploaded", uploaded_by=user.id
    )
    if user.institution_id:
        batch["institution_id"] = user.institution_id
    return {
        "batch": batch,
        "suggested_mapping": suggestion.mapping,
        "unmapped_columns": suggestion.unmapped,
        "missing_required": suggestion.missing_required,
    }


@router.post("/{batch_id}/mapping", response_model=Batch)
def set_mapping(
    batch_id: str,
    body: MappingRequest,
    user: User = Depends(UPLOADERS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Replace the column mapping, then re-validate every row."""
    if real:
        with transaction() as conn:
            return service.batch_out(
                service.apply_mapping(conn, batch_id, body.mapping, user, settings)
            )
    batch = _mock_batch(batch_id)
    batch["status"] = "mapped"
    return batch


@router.get("/{batch_id}", response_model=Batch)
def get_batch(batch_id: str, user: User = Depends(READERS), real: bool = Depends(REAL)) -> dict:
    if real:
        with transaction() as conn:
            return service.batch_out(service.load_batch(conn, batch_id, user))
    return _mock_batch(batch_id)


@router.get("/{batch_id}/issues", response_model=list[ValidationIssue])
def get_issues(
    batch_id: str, user: User = Depends(READERS), real: bool = Depends(REAL)
) -> list[dict]:
    if real:
        with transaction() as conn:
            return service.issues(conn, batch_id, user)
    _mock_batch(batch_id)
    return mock("batch_issues")


def _after_commit(
    background: BackgroundTasks,
    events: list[service.Event],
    webhook: tuple[str, str] | None,
    batch_id: str,
    settings: Settings,
) -> None:
    """Broadcast, POST batch.committed to the institution's webhook, and run the
    cross-institution Blind Match for the batch's students (all best effort)."""
    background.add_task(realtime.publish, events)
    if webhook:
        for name, payload in events:
            if name == "batch.committed":
                background.add_task(outbound_webhooks.deliver, *webhook, name, payload)
    if events and settings.is_real("blind_match"):
        background.add_task(blind_match.match_after_commit, batch_id)


@router.post("/{batch_id}/commit", response_model=CommitResult)
def commit_batch(
    batch_id: str,
    background: BackgroundTasks,
    user: User = Depends(INTEGRATORS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Commit valid rows to the Seat Ledger in one transaction. Idempotent.

    409 SUBMISSION_WINDOW_CLOSED outside the academic year's window. Accepts X-API-Key.
    """
    if real:
        with transaction() as conn:
            result, events = service.commit(conn, batch_id, user, settings)
            webhook = (
                institutions.webhook_target(conn, user.institution_id, settings.webhook_key)
                if events and user.institution_id
                else None
            )
        _after_commit(background, events, webhook, result["batch_id"], settings)
        return result
    _mock_batch(batch_id)
    return mock("commit_result")


@router.post("/{batch_id}/corrections", response_model=CommitResult)
async def upload_corrections(
    batch_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(INTEGRATORS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Upload a corrected file for the rows this committed batch rejected.

    The file is stored as a new batch linked by parent_batch_id, re-validated, and only rows
    matching a rejected row are committed: by a source_row column holding the original row
    number, else by APAAR ID, provisional ID, or name and date of birth. Fixed rows have
    their error findings in the original batch resolved.
    """
    name = file.filename or "corrections.csv"
    content = await file.read()
    if real:
        with transaction() as conn:
            result, events = service.correct(conn, batch_id, user, name, content, settings)
            webhook = (
                institutions.webhook_target(conn, user.institution_id, settings.webhook_key)
                if events and user.institution_id
                else None
            )
        _after_commit(background, events, webhook, result["batch_id"], settings)
        return result
    _mock_batch(batch_id)
    result = mock("commit_result")
    result.update(
        batch_id="30000000-0000-4000-8000-000000000002",
        rows_committed=4,
        rows_rejected=0,
        review_cases_created=[],
        parent_batch_id=batch_id,
    )
    return result
