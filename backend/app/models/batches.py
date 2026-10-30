# Owner: Dev B
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.rule_codes import RuleCode
from app.models.common import BatchStatus, IssueSeverity


class BatchCounts(BaseModel):
    rows_total: int = 0
    errors: int = 0
    warnings: int = 0
    review: int = 0
    info: int = 0


class Batch(BaseModel):
    id: str
    institution_id: str
    uploaded_by: str
    file_name: str
    file_hash: str
    status: BatchStatus
    counts: BatchCounts
    created_at: datetime
    parent_batch_id: str | None = Field(
        None, description="Set on a correction batch: the batch whose rejected rows it fixes"
    )


class BatchList(BaseModel):
    """One page of batches, newest first. total counts every match, not just this page."""

    items: list[Batch]
    total: int
    limit: int
    offset: int


class BatchUploadResult(BaseModel):
    batch: Batch
    suggested_mapping: dict[str, str] = Field(
        description="Uploaded column name -> admissions-template column name"
    )
    unmapped_columns: list[str]
    missing_required: list[str] = []
    duplicate_upload: bool = False


class MappingRequest(BaseModel):
    mapping: dict[str, str]


class ValidationIssue(BaseModel):
    id: int
    batch_id: str
    row_number: int
    rule_code: RuleCode
    severity: IssueSeverity
    message: str
    details: dict[str, Any] = {}
    resolved: bool = False
    resolution_note: str | None = None
    resolved_at: datetime | None = None


class ResolveIssueRequest(BaseModel):
    note: str = Field(min_length=1)


class CommitResult(BaseModel):
    batch_id: str
    status: BatchStatus
    rows_committed: int
    rows_rejected: int
    rows_skipped_existing: int = 0
    review_cases_created: list[str]
    parent_batch_id: str | None = Field(
        None, description="Set on a correction commit: the batch whose rejected rows it fixes"
    )
    rows_not_matched: int = Field(
        0, description="Correction rows that matched no rejected row of the parent batch"
    )
