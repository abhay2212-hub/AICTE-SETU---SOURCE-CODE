# Owner: Dev B
"""F12 enrolment certificates: a one-page PDF whose QR code is a standard signed credential.

The QR carries a credential in the shared/credentials.md format with audience
"enrolment-certificate", the four allowed claims and a 180-day lifetime, so any credential
verifier accepts it unchanged. The certificate ID is that credential's ID: revoking the
credential revokes the certificate. The full APAAR ID never appears in the PDF or the QR.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi import HTTPException, status
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from app.core.security import INSTITUTION_ROLES, scoped_institution
from app.models.auth import User
from app.services import audit_store
from app.services import credentials as creds
from app.services.batches import as_uuid
from app.services.validation import mask_apaar

AUDIENCE = "enrolment-certificate"
DEFAULT_ACADEMIC_YEAR = "2026-27"
OPTED_OUT_LINE = "APAAR ID: not provided (opted out)"
PLATFORM = "APAAR Integrity Platform"
FOOTER = "Synthetic demonstration data. Issued by APAAR Integrity Platform."
ACCESS_PURPOSE = "enrolment certificate issued"
ACCESS_FIELDS = [
    "academic_year",
    "admission_date",
    "admission_status",
    "apaar_id_masked",
    "institution",
    "programme",
    "student_name",
]


def no_valid_admission(academic_year: str) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "code": "NO_VALID_ADMISSION",
            "message": f"No active, valid admission for {academic_year}; no certificate issued",
        },
    )


def ensure_not_disputed(admission: dict[str, Any]) -> None:
    """A disputed admission is under review, so it cannot be certified (409)."""
    if admission["status"] == "student_disputed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "ADMISSION_DISPUTED",
                "message": "This admission is disputed by the student and under review",
            },
        )


# ---------------------------------------------------------------------------- pure builders
def build_credential(
    student_id: str,
    admission: dict[str, Any],
    seed_hex: str,
    pseudonym_secret: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    """(payload, qr_text) of the certificate's credential: all four claims, 180 days."""
    claims = creds.claim_values(admission, list(creds.CLAIMS))
    payload = creds.build_payload(
        student_id=student_id,
        audience=AUDIENCE,
        claims=claims,
        expiry=creds.CERTIFICATE_EXPIRY,
        pseudonym_secret=pseudonym_secret,
        now=now,
    )
    return payload, creds.sign(payload, creds.signing_key(seed_hex))


def apaar_line(student: dict[str, Any]) -> str:
    masked = mask_apaar(student.get("apaar_id"))
    if student.get("opted_out") or not masked:
        return OPTED_OUT_LINE
    return f"APAAR ID: {masked}"


def certificate_fields(
    student: dict[str, Any],
    admission: dict[str, Any],
    payload: dict[str, Any],
    qr_text: str,
    frontend_url: str,
) -> dict[str, Any]:
    """Everything printed on the certificate. Holds only the masked APAAR ID."""
    issued = datetime.fromtimestamp(payload["iat"], UTC)
    return {
        "certificate_id": payload["id"],
        "student_id": str(student["id"]),
        "student_name": student["full_name"],
        "provisional_id": student.get("provisional_id"),
        "apaar_id_masked": None
        if student.get("opted_out")
        else mask_apaar(student.get("apaar_id")),
        "apaar_line": apaar_line(student),
        "programme_name": admission["programme"],
        "programme_code": admission["programme_code"],
        "institution_name": admission["institution"],
        "aicte_code": admission["aicte_code"],
        "academic_year": admission["academic_year"],
        "admission_date": str(admission["admission_date"]),
        "admission_status": admission["status"],
        "issued_at": issued,
        "expires_at": datetime.fromtimestamp(payload["exp"], UTC),
        "verify_url": f"{frontend_url}/verifier" if frontend_url else "/verifier",
        "qr_text": qr_text,
    }


def render_pdf(cert: dict[str, Any], compress: bool = True) -> bytes:
    """One A4 page: title, details table, QR bottom-right, footer.

    ``compress=False`` keeps the page text readable in the raw bytes, for tests."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1 if compress else 0)
    pdf.setTitle(f"Certificate of Enrolment {cert['certificate_id']}")
    pdf.setAuthor(PLATFORM)
    width, height = A4
    margin = 20 * mm

    pdf.setStrokeColor(colors.HexColor("#1e1b6b"))
    pdf.setLineWidth(2)
    pdf.rect(margin / 2, margin / 2, width - margin, height - margin)

    pdf.setFillColor(colors.HexColor("#4f46e5"))
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(margin, height - margin - 6 * mm, PLATFORM.upper())
    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(margin, height - margin - 18 * mm, "Certificate of Enrolment")
    pdf.setFont("Helvetica", 10)
    pdf.setFillColor(colors.HexColor("#475569"))
    pdf.drawString(
        margin,
        height - margin - 26 * mm,
        f"Certificate ID {cert['certificate_id']} · issued {cert['issued_at']:%d %B %Y}",
    )

    identifier = (
        ("Provisional ID", cert["provisional_id"])
        if cert["provisional_id"]
        else ("Student ID", cert["student_id"])
    )
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=10, leading=13)
    rows = [
        ("Certificate ID", cert["certificate_id"]),
        ("Student name", cert["student_name"]),
        identifier,
        ("APAAR", cert["apaar_line"]),
        ("Programme", f"{cert['programme_name']} ({cert['programme_code']})"),
        ("Institution", f"{cert['institution_name']} (AICTE {cert['aicte_code']})"),
        ("Academic year", cert["academic_year"]),
        ("Admission date", cert["admission_date"]),
        ("Admission status", cert["admission_status"].replace("_", " ")),
        ("Issued on", f"{cert['issued_at']:%Y-%m-%d}"),
        ("Valid until", f"{cert['expires_at']:%Y-%m-%d}"),
    ]
    table = Table(
        [[Paragraph(f"<b>{k}</b>", cell), Paragraph(str(v), cell)] for k, v in rows],
        colWidths=[45 * mm, width - 2 * margin - 45 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    _, table_height = table.wrapOn(pdf, width - 2 * margin, height)
    table.drawOn(pdf, margin, height - margin - 36 * mm - table_height)

    # Error level L keeps the ~740-character credential at the fewest, largest modules,
    # which phone cameras read most reliably.
    qr_size = 66 * mm
    widget = QrCodeWidget(cert["qr_text"], barLevel="L")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(
        qr_size, qr_size, transform=[qr_size / (x1 - x0), 0, 0, qr_size / (y1 - y0), 0, 0]
    )
    drawing.add(widget)
    qr_x, qr_y = width - margin - qr_size, margin + 16 * mm
    renderPDF.draw(drawing, pdf, qr_x, qr_y)

    caption = ParagraphStyle("caption", fontName="Helvetica", fontSize=9, leading=12)
    note = Paragraph(
        f"Verify by scanning the QR code at <b>{cert['verify_url']}</b>. The QR is a signed "
        "credential: its signature, expiry and revocation can be checked offline or online.",
        caption,
    )
    note_width = width - 2 * margin - qr_size - 8 * mm
    _, note_height = note.wrapOn(pdf, note_width, qr_size)
    note.drawOn(pdf, margin, qr_y + qr_size - note_height)

    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.HexColor("#64748b"))
    pdf.drawString(margin, margin, FOOTER)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------- database
def _student(conn: psycopg.Connection, student_id: str) -> dict[str, Any]:
    row = (
        conn.execute(
            "select id, full_name, apaar_id, provisional_id, opted_out from public.students"
            " where id = %s",
            (student_id,),
        ).fetchone()
        if as_uuid(student_id)
        else None
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Student '{student_id}' not found")
    return row


def _valid_admission(
    conn: psycopg.Connection, student_id: str, academic_year: str
) -> dict[str, Any]:
    """Most recent active, non-withdrawn admission for the year, or 409."""
    row = conn.execute(
        """
        select a.id, a.status::text as status, a.academic_year, a.admission_date,
               p.name as programme, p.code as programme_code,
               i.id as institution_id, i.name as institution, i.aicte_code
        from public.admissions a
        join public.programmes p on p.id = a.programme_id
        join public.institutions i on i.id = p.institution_id
        where a.student_id = %s and a.academic_year = %s
          and a.active and a.status <> 'withdrawn'
        order by a.created_at desc limit 1
        """,
        (student_id, academic_year),
    ).fetchone()
    if row is None:
        raise no_valid_admission(academic_year)
    return row


def check_institution(user: User, institution_id: str) -> None:
    """Institution users may only certify admissions at their own institution (403)."""
    if user.role in INSTITUTION_ROLES:
        scoped_institution(user, institution_id)


def issue(
    conn: psycopg.Connection,
    student_id: str,
    academic_year: str,
    user: User,
    seed_hex: str,
    pseudonym_secret: str,
    frontend_url: str,
) -> dict[str, Any]:
    """Issue, record and log one certificate; the caller has already checked the role."""
    if not pseudonym_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PSEUDONYM_SECRET is not set")
    student = _student(conn, student_id)
    admission = _valid_admission(conn, student_id, academic_year)
    check_institution(user, str(admission["institution_id"]))
    ensure_not_disputed(admission)
    payload, qr_text = build_credential(student_id, admission, seed_hex, pseudonym_secret)
    creds.store(conn, payload, student_id, str(admission["id"]))
    actor = f"student:{student_id}" if user.role == "student" else user.id
    audit_store.append_event(
        conn,
        actor,
        "certificate.issued",
        "credential",
        payload["id"],
        {"student_id": student_id, "admission_id": str(admission["id"])},
    )
    accessor = "Student portal" if user.role == "student" else (user.display_name or user.role)
    creds.log_access(conn, student_id, accessor[:200], user.role, ACCESS_PURPOSE, ACCESS_FIELDS)
    return certificate_fields(student, admission, payload, qr_text, frontend_url)


# ---------------------------------------------------------------------------- fixtures
def fixture_certificate(
    students: dict[str, Any],
    admissions: list[dict[str, Any]],
    institutions: list[dict[str, Any]],
    student_id: str,
    academic_year: str,
    user: User,
    frontend_url: str,
) -> dict[str, Any]:
    """Fixture mode: same certificate from the JSON fixtures, signed with the TEST seed."""
    student = students.get(student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Student '{student_id}' not found")
    admission = next(
        (
            a
            for a in admissions
            if a["student_id"] == student_id
            and a["academic_year"] == academic_year
            and a["status"] != "withdrawn"
        ),
        None,
    )
    if admission is None:
        raise no_valid_admission(academic_year)
    check_institution(user, admission["institution_id"])
    ensure_not_disputed(admission)
    institution = next(i for i in institutions if i["id"] == admission["institution_id"])
    programme = next(
        (p for p in institution.get("programmes", []) if p["id"] == admission["programme_id"]),
        {"name": student["programme_name"], "code": admission["programme_code"]},
    )
    row = {
        "id": admission["id"],
        "status": admission["status"],
        "academic_year": admission["academic_year"],
        "admission_date": admission["admission_date"],
        "programme": programme["name"],
        "programme_code": programme["code"],
        "institution_id": institution["id"],
        "institution": institution["name"],
        "aicte_code": institution["aicte_code"],
    }
    payload, qr_text = build_credential(
        student_id, row, creds.TEST_SEED_HEX, creds.TEST_PSEUDONYM_SECRET
    )
    return certificate_fields(student, row, payload, qr_text, frontend_url)


def short_id(certificate_id: str) -> str:
    return certificate_id.split("-")[0]
