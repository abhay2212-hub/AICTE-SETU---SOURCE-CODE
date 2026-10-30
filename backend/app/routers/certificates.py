# Owner: Dev B (F12, taken over from Dev C)
"""Enrolment certificates (F12): PDF with a QR that is a standard signed credential."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response

from app.core.config import Settings, get_settings
from app.core.datasource import source
from app.core.db import transaction
from app.core.security import require_roles
from app.mocks import mock
from app.models.auth import User
from app.models.certificates import Certificate
from app.services import certificates as service
from app.services import students

router = APIRouter(tags=["certificates"])

VIEWERS = require_roles(
    "student", "institution_admin", "institution_operator", "aicte_admin", "auditor"
)
STUDENT = require_roles("student")
REAL = source("certificates")
DEMO_STUDENT = Header(
    default=None, description="MOCK_MODE only: act as this student id instead of the demo one"
)
YEAR = Query(service.DEFAULT_ACADEMIC_YEAR, description="Academic year of the admission")
PDF_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "content": {"application/pdf": {}},
        "description": "The certificate PDF (format=pdf), or its details as JSON",
        "headers": {"X-Certificate-Id": {"description": "Certificate (credential) ID"}},
    },
    409: {"description": "NO_VALID_ADMISSION: no active, valid admission for the year"},
}


def _own_student_id(user: User, x_demo_student: str | None, conn=None) -> str:
    if conn is not None:
        return students.resolve_student_id(conn, user, x_demo_student)
    return students.fixture_student_id(user, x_demo_student)


def _certificate(
    student_id: str | None,
    academic_year: str,
    user: User,
    real: bool,
    settings: Settings,
    x_demo_student: str | None,
) -> dict[str, Any]:
    """Issue the certificate for ``student_id`` (None: the signed-in student)."""
    if real:
        with transaction() as conn:
            if user.role == "student":
                own = _own_student_id(user, x_demo_student, conn)
                if student_id is not None and student_id != own:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN, "Students can only fetch their own certificate"
                    )
                student_id = own
            return service.issue(
                conn,
                student_id,
                academic_year,
                user,
                settings.credential_signing_key,
                settings.pseudonym_secret,
                settings.frontend_base_url,
            )
    if user.role == "student":
        own = _own_student_id(user, x_demo_student)
        if student_id is not None and student_id != own:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Students can only fetch their own certificate"
            )
        student_id = own
    return service.fixture_certificate(
        mock("students"),
        mock("admissions"),
        mock("institutions"),
        student_id,
        academic_year,
        user,
        settings.frontend_base_url,
    )


def _pdf(cert: dict[str, Any]) -> Response:
    name = f"certificate-{service.short_id(cert['certificate_id'])}.pdf"
    return Response(
        service.render_pdf(cert),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Certificate-Id": cert["certificate_id"],
        },
    )


def _json(cert: dict[str, Any]) -> dict[str, Any]:
    return {
        "certificate_no": cert["certificate_id"],
        "student_id": cert["student_id"],
        "apaar_id": cert["apaar_id_masked"],
        "provisional_id": cert["provisional_id"],
        "student_name": cert["student_name"],
        "institution_name": cert["institution_name"],
        "programme_name": cert["programme_name"],
        "academic_year": cert["academic_year"],
        "issued_at": cert["issued_at"],
        "verify_url": cert["verify_url"],
        "qr_text": cert["qr_text"],
        "expires_at": cert["expires_at"],
    }


@router.get("/certificates/{student_id}", response_model=Certificate, responses=PDF_RESPONSES)
def get_certificate(
    student_id: str,
    format: Literal["json", "pdf"] = Query("json", description="json details or the PDF"),
    academic_year: str = YEAR,
    user: User = Depends(VIEWERS),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
    x_demo_student: str | None = DEMO_STUDENT,
):
    """Issue an enrolment certificate. The APAAR ID is masked; opted-out students get one.

    Students: their own only. Institution users: students admitted at their institution.
    AICTE admins and auditors: anyone. Each call issues a new certificate (credential).
    """
    cert = _certificate(student_id, academic_year, user, real, settings, x_demo_student)
    return _pdf(cert) if format == "pdf" else _json(cert)


@router.get(
    "/students/me/certificate",
    response_class=Response,
    responses=PDF_RESPONSES,
    tags=["students"],
)
def my_certificate(
    academic_year: str = YEAR,
    user: User = Depends(STUDENT),
    real: bool = Depends(REAL),
    settings: Settings = Depends(get_settings),
    x_demo_student: str | None = DEMO_STUDENT,
) -> Response:
    """The signed-in student's own enrolment certificate as a PDF."""
    return _pdf(_certificate(None, academic_year, user, real, settings, x_demo_student))
