# Owner: Dev C
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles, scoped_institution
from app.mocks import mock, not_found
from app.models.auth import User
from app.models.common import ReportFormat
from app.models.reports import AccreditationReport, EnrolmentReport, GroupBy, StateReport
from app.services import integrity_store, state_report
from app.services import report_aggregations as aggregations
from app.services.institutions import get_institution
from app.services.reports import to_pdf, to_xlsx

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
)
# Enrolment is AICTE-wide, so institution users may only read their own accreditation report.
ENROLMENT_READERS = require_roles("aicte_admin", "auditor")
ACCREDITATION_READERS = require_roles("aicte_admin", "auditor", "institution_admin")
REAL = source("reports")
ACADEMIC_YEAR = "2026-27"
NOT_COMPUTED = f"Integrity score not yet computed for {ACADEMIC_YEAR}"

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FILE_RESPONSES = {
    200: {
        "content": {"application/pdf": {}, XLSX: {}},
        "description": "JSON, or the file when format=pdf or format=xlsx",
    }
}


def _file(
    name: str, fmt: str, title: str, rows: list[dict], summary: list[str] | None = None
) -> Response:
    if fmt == "xlsx":
        body, media = to_xlsx(rows), XLSX
    else:
        lines = [", ".join(f"{k}: {v}" for k, v in r.items()) for r in rows]
        body, media = to_pdf(title, [*(summary or []), *lines]), "application/pdf"
    return Response(
        body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'},
    )


def _frame(rows: list[dict], columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame([dict(row) for row in rows], columns=columns)


def _enrolment_report(conn, group_by: GroupBy) -> dict:
    rows = conn.execute(
        """
        select p.code as programme_code, i.state, s.category, s.gender, s.opted_out
        from public.admissions a
        join public.students s on s.id = a.student_id
        join public.programmes p on p.id = a.programme_id
        join public.institutions i on i.id = p.institution_id
        where a.active and a.academic_year = %s
        """,
        (ACADEMIC_YEAR,),
    ).fetchall()
    admissions = _frame(rows, ["programme_code", "state", "category", "gender", "opted_out"])
    grouped = aggregations.enrolment_rows(admissions, group_by)
    return {
        "academic_year": ACADEMIC_YEAR,
        "group_by": group_by,
        "total": int(grouped["admissions"].sum()) if not grouped.empty else 0,
        "rows": grouped.to_dict("records"),
    }


def _accreditation_report(conn, institution_id: str, user: User) -> dict:
    # Scopes to the user's institution and 404s unknown or malformed ids.
    institution = get_institution(conn, institution_id, user)
    admissions_rows = conn.execute(
        """
        select a.programme_id, p.code as programme_code, s.category,
               (s.apaar_id is not null) as has_apaar
        from public.admissions a
        join public.students s on s.id = a.student_id
        join public.programmes p on p.id = a.programme_id
        where a.active and p.institution_id = %s and a.academic_year = %s
        """,
        (institution_id, ACADEMIC_YEAR),
    ).fetchall()
    intake_rows = conn.execute(
        """
        select sp.programme_id, p.code as programme_code, sp.pool::text as pool,
               sp.approved_seats, sp.rule_version
        from public.seat_pools sp
        join public.programmes p on p.id = sp.programme_id
        where p.institution_id = %s and sp.academic_year = %s
        """,
        (institution_id, ACADEMIC_YEAR),
    ).fetchall()
    score = integrity_store.latest_for(conn, institution_id, ACADEMIC_YEAR)
    review_cases = conn.execute(
        """
        select count(*) as n from public.review_cases
        where institution_id = %s and status = 'open'
          and (evidence->>'academic_year' = %s or evidence->>'academic_year' is null)
        """,
        (institution_id, ACADEMIC_YEAR),
    ).fetchone()
    admissions = _frame(
        admissions_rows, ["programme_id", "programme_code", "category", "has_apaar"]
    )
    intake = _frame(
        intake_rows,
        ["programme_id", "programme_code", "pool", "approved_seats", "rule_version"],
    )
    apaar_coverage = 0.0
    if not admissions.empty:
        with_apaar = int(admissions["has_apaar"].fillna(False).astype(bool).sum())
        apaar_coverage = round(100 * with_apaar / len(admissions), 1)
    return aggregations.accreditation_report(
        {"institution_id": institution["id"], "institution_name": institution["name"]},
        admissions,
        intake,
        academic_year=ACADEMIC_YEAR,
        integrity_score=score["score"] if score else None,
        apaar_coverage_pct=apaar_coverage,
        open_review_cases=int(review_cases["n"]),
        integrity_note=None if score else NOT_COMPUTED,
    )


@router.get("/enrolment", response_model=EnrolmentReport, responses=FILE_RESPONSES)
def enrolment(
    group_by: GroupBy = Query("state"),
    format: ReportFormat = Query("json"),
    user: User = Depends(ENROLMENT_READERS),
    real: bool = Depends(REAL),
):
    if real:
        with transaction() as conn:
            report = _enrolment_report(conn, group_by)
    else:
        report = mock("enrolment_report")[group_by]
    if format == "json":
        return report
    title = f"Enrolment {report['academic_year']} by {group_by}"
    return _file(f"enrolment-{group_by}", format, title, report["rows"])


@router.get("/states", response_model=StateReport)
def states(
    academic_year: str = Query(ACADEMIC_YEAR),
    user: User = Depends(ENROLMENT_READERS),
    real: bool = Depends(REAL),
) -> dict:
    """Per state: institutions, active admissions against approved seats, programmes over
    intake, open review cases and the average Integrity Score. Aggregates only."""
    if real:
        with transaction() as conn:
            return state_report.from_db(conn, academic_year)
    report = mock("state_report").get(academic_year)
    if report is None:
        raise not_found("State report", academic_year)
    return report


@router.get(
    "/accreditation/{institution_id}",
    response_model=AccreditationReport,
    responses=FILE_RESPONSES,
)
def accreditation(
    institution_id: str,
    format: ReportFormat = Query("json"),
    user: User = Depends(ACCREDITATION_READERS),
    real: bool = Depends(REAL),
):
    institution_id = scoped_institution(user, institution_id)
    if real:
        with transaction() as conn:
            report = _accreditation_report(conn, institution_id, user)
    else:
        report = mock("accreditation").get(institution_id)
        if report is None:
            raise not_found("Institution", institution_id)
    if format == "json":
        return report
    score = report["integrity_score"]
    summary = [
        f"Integrity score: {report.get('integrity_note') if score is None else score}",
        f"APAAR coverage: {report['apaar_coverage_pct']}%",
        f"Open review cases: {report['open_review_cases']}",
    ]
    title = f"Accreditation summary: {report['institution_name']}"
    return _file(f"accreditation-{institution_id}", format, title, report["programmes"], summary)
