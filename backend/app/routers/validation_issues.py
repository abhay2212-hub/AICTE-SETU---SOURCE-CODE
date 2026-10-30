# Owner: Dev B
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.batches import ResolveIssueRequest, ValidationIssue
from app.services import batches as service

router = APIRouter(prefix="/validation-issues", tags=["batches"])

RESOLVERS = require_roles("institution_admin", "aicte_admin")


@router.post("/{issue_id}/resolve", response_model=ValidationIssue)
def resolve_issue(
    issue_id: int,
    body: ResolveIssueRequest,
    user: User = Depends(RESOLVERS),
    real: bool = Depends(source("batches")),
) -> dict:
    """Resolve a finding with a note. Warnings and info: institution_admin or aicte_admin.
    Review findings: aicte_admin only. Errors (409) are fixed with a correction upload."""
    if real:
        with transaction() as conn:
            return service.resolve_issue(conn, issue_id, body.note, user)
    issue = next((i for i in mock("batch_issues") if i["id"] == issue_id), None)
    if issue is None:
        raise not_found("Validation issue", str(issue_id))
    service.check_resolvable(issue["severity"], user, issue["batch_id"])
    issue.update(resolved=True, resolution_note=body.note, resolved_at=datetime.now(UTC))
    return issue
