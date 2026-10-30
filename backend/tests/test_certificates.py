# Owner: Dev B
"""F12 enrolment certificates: PDF, credential QR, APAAR masking, scoping, revocation."""

from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.auth import User
from app.routers import certificates as cert_router
from app.routers import credentials as cred_router
from app.services import certificates as service
from app.services import credentials as creds
from tests.conftest import as_role

STUDENT = "40000000-0000-4000-8000-000000000001"  # Meghdoot, APAAR 999912340001
OPTED_OUT = "40000000-0000-4000-8000-000000000006"  # Narmada, provisional ID only
MEGHDOOT = "10000000-0000-4000-8000-000000000001"
NARMADA = "10000000-0000-4000-8000-000000000002"
FULL_APAAR = "999912340001"
AICTE = as_role("aicte_admin")

ADMISSION = {
    "id": uuid.UUID("50000000-0000-4000-8000-000000000001"),
    "status": "student_confirmed",
    "academic_year": "2026-27",
    "admission_date": date(2026, 8, 5),
    "programme": "B.Tech Computer Science and Engineering",
    "programme_code": "UG-CSE",
    "institution_id": uuid.UUID(MEGHDOOT),
    "institution": "Meghdoot Institute of Engineering",
    "aicte_code": "1-9999001",
}
STUDENT_ROW = {
    "id": uuid.UUID(STUDENT),
    "full_name": "Aarav Sharma",
    "apaar_id": FULL_APAAR,
    "provisional_id": None,
    "opted_out": False,
}
AICTE_USER = User(id="demo-aicte_admin", role="aicte_admin", demo=True)


def fixture_cert(student_id: str = STUDENT, user: User = AICTE_USER) -> dict:
    from app.mocks import mock

    return service.fixture_certificate(
        mock("students"),
        mock("admissions"),
        mock("institutions"),
        student_id,
        "2026-27",
        user,
        "https://demo.example",
    )


# ---------------------------------------------------------------------------- builders
def test_credential_is_standard_180_day_certificate_credential():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    payload, qr_text = service.build_credential(
        STUDENT, ADMISSION, creds.TEST_SEED_HEX, creds.TEST_PSEUDONYM_SECRET, now=now
    )
    key = creds.signing_key(creds.TEST_SEED_HEX).verify_key
    result = creds.check(qr_text, key, set(), now=now + timedelta(days=179))
    assert result["valid"] is True
    assert payload["aud"] == "enrolment-certificate"
    assert set(payload["claims"]) == set(creds.CLAIMS)
    assert payload["exp"] - payload["iat"] == 180 * 24 * 3600
    assert creds.check(qr_text, key, set(), now=now + timedelta(days=180))["reason"] == "expired"
    assert creds.check(qr_text, key, {payload["id"]}, now=now)["reason"] == "revoked"


def test_student_api_expiry_choices_unchanged():
    from typing import get_args

    from app.models.credentials import Expiry

    assert get_args(Expiry) == ("15m", "1d", "7d")
    assert set(creds.EXPIRY) == {"15m", "1d", "7d"}


def test_full_apaar_never_in_pdf_or_qr():
    cert = fixture_cert()
    payload, _ = creds.decode(cert["qr_text"])
    assert FULL_APAAR not in json.dumps(payload)
    assert FULL_APAAR not in cert["qr_text"]
    assert FULL_APAAR not in json.dumps(cert, default=str)
    pdf = service.render_pdf(cert, compress=False)
    assert FULL_APAAR.encode() not in pdf
    assert b"XXXX-XXXX-0001" in pdf


def test_opted_out_student_gets_certificate_with_provisional_id():
    cert = fixture_cert(OPTED_OUT)
    assert cert["apaar_line"] == "APAAR ID: not provided (opted out)"
    assert cert["apaar_id_masked"] is None
    pdf = service.render_pdf(cert, compress=False)
    assert b"APAAR ID: not provided \\(opted out\\)" in pdf
    assert b"PROV-1-9999002-0001" in pdf


def test_pdf_has_required_contents_on_one_page():
    pdf = service.render_pdf(fixture_cert(), compress=False)
    for text in (
        b"Certificate of Enrolment",
        b"Aarav Sharma",
        b"UG-CSE",
        b"1-9999001",
        b"2026-08-05",
        b"student confirmed",
        b"https://demo.example/verifier",
        b"Synthetic demonstration data. Issued by APAAR Integrity Platform.",
    ):
        assert text in pdf, text
    assert len(re.findall(rb"/Type\s*/Page(?!s)", pdf)) == 1


# ---------------------------------------------------------------------------- fixture mode
def test_student_downloads_own_certificate_pdf(client):
    r = client.get("/students/me/certificate", headers=as_role("student"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert r.headers["X-Mock"] == "true"
    cert_id = r.headers["X-Certificate-Id"]
    assert uuid.UUID(cert_id)
    assert (
        r.headers["content-disposition"]
        == f'attachment; filename="certificate-{cert_id.split("-")[0]}.pdf"'
    )


def test_existing_path_still_returns_json_by_default(client):
    r = client.get(f"/certificates/{STUDENT}", headers=AICTE)
    assert r.status_code == 200
    assert r.headers["X-Mock"] == "true"
    body = r.json()
    assert body["apaar_id"] == "XXXX-XXXX-0001"
    assert body["verify_url"].endswith("/verifier")
    verified = client.post("/credentials/verify", json={"qr_text": body["qr_text"]}).json()
    assert verified["valid"] is True
    assert verified["claims"]["institution"] == "Meghdoot Institute of Engineering"


def test_format_pdf_on_existing_path(client):
    r = client.get(f"/certificates/{OPTED_OUT}", params={"format": "pdf"}, headers=AICTE)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert "X-Certificate-Id" in r.headers


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        (as_role("student"), 200),
        ({**as_role("student"), "X-Demo-Student": OPTED_OUT}, 403),
        (as_role("institution_admin", MEGHDOOT), 200),
        (as_role("institution_operator", MEGHDOOT), 200),
        (as_role("institution_admin", NARMADA), 403),
        (as_role("aicte_admin"), 200),
        (as_role("auditor"), 200),
        (as_role("verifier"), 403),
    ],
)
def test_scoping(client, headers, expected):
    r = client.get(f"/certificates/{STUDENT}", params={"format": "pdf"}, headers=headers)
    assert r.status_code == expected, r.text


def test_no_admission_for_year_is_409(client):
    r = client.get(f"/certificates/{STUDENT}", params={"academic_year": "2025-26"}, headers=AICTE)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NO_VALID_ADMISSION"


# ---------------------------------------------------------------------------- real mode
class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self, admission: dict | None = ADMISSION):
        self.admission = admission
        self.calls: list[tuple[str, tuple]] = []
        self.credentials: dict[str, str] = {}
        self.revoked: set[str] = set()

    def execute(self, sql: str, params: tuple = ()):
        self.calls.append((sql, params))
        if "from public.students where is_demo" in sql or sql.startswith(
            "select id from public.students"
        ):
            return FakeCursor([{"id": uuid.UUID(STUDENT)}])
        if "from public.students" in sql:
            return FakeCursor([STUDENT_ROW] if params[0] == STUDENT else [])
        if "from public.admissions a" in sql:
            return FakeCursor([self.admission] if self.admission else [])
        if "insert into public.credentials" in sql:
            self.credentials[str(params[0])] = str(params[1])
            return FakeCursor([])
        if "insert into public.access_log" in sql:
            return FakeCursor([])
        if "from public.credential_revocations" in sql:
            return FakeCursor([{"?column?": 1}] if params[0] in self.revoked else [])
        if "select student_id from public.credentials" in sql:
            owner = self.credentials.get(str(params[0]))
            return FakeCursor([{"student_id": owner}] if owner else [])
        raise AssertionError(f"unexpected query: {sql}")


@pytest.fixture
def real_db(settings_override, monkeypatch):
    settings_override(
        real_domains="certificates,credentials",
        credential_signing_key=creds.TEST_SEED_HEX,
        pseudonym_secret="unit-test-secret",
        frontend_url="https://apaar.example",
    )
    conn = FakeConn()

    @contextmanager
    def fake_transaction():
        yield conn

    events: list[tuple] = []
    monkeypatch.setattr(cert_router, "transaction", fake_transaction)
    monkeypatch.setattr(cred_router, "transaction", fake_transaction)
    monkeypatch.setattr(service.audit_store, "append_event", lambda *a: events.append(a))
    conn.events = events
    return conn


def test_real_issue_records_credential_audit_and_access_log(client, real_db):
    r = client.get("/students/me/certificate", headers=as_role("student"))
    assert r.status_code == 200, r.text
    assert r.headers["X-Mock"] == "false"
    cert_id = r.headers["X-Certificate-Id"]
    assert real_db.credentials == {cert_id: STUDENT}

    admission_sql, params = next(c for c in real_db.calls if "from public.admissions a" in c[0])
    assert "a.active" in admission_sql and "a.status <> 'withdrawn'" in admission_sql
    assert params == (STUDENT, "2026-27")

    (event,) = real_db.events
    assert event[1:5] == (
        f"student:{STUDENT}",
        "certificate.issued",
        "credential",
        cert_id,
    )
    assert event[5] == {"student_id": STUDENT, "admission_id": str(ADMISSION["id"])}
    log_sql, log_params = next(c for c in real_db.calls if "insert into public.access_log" in c[0])
    assert log_params[:4] == (STUDENT, "Student portal", "student", "enrolment certificate issued")
    assert FULL_APAAR not in json.dumps(real_db.events, default=str)


def test_real_withdrawn_only_is_409(client, real_db):
    real_db.admission = None
    r = client.get(f"/certificates/{STUDENT}", headers=AICTE)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NO_VALID_ADMISSION"
    assert not any("insert into" in sql for sql, _ in real_db.calls)


def test_real_institution_scoping(client, real_db):
    ok = client.get(f"/certificates/{STUDENT}", headers=as_role("institution_admin", MEGHDOOT))
    assert ok.status_code == 200
    other = client.get(f"/certificates/{STUDENT}", headers=as_role("institution_admin", NARMADA))
    assert other.status_code == 403
    assert len(real_db.credentials) == 1


def test_revoked_certificate_fails_verification(client, real_db):
    body = client.get(f"/certificates/{STUDENT}", headers=AICTE).json()
    assert body["verify_url"] == "https://apaar.example/verifier"
    first = client.post("/credentials/verify", json={"qr_text": body["qr_text"]}).json()
    assert first["valid"] is True
    real_db.revoked.add(body["certificate_no"])
    second = client.post("/credentials/verify", json={"qr_text": body["qr_text"]}).json()
    assert second == {"valid": False, "reason": "revoked", "expires_at": second["expires_at"]}


DISPUTED = "40000000-0000-4000-8000-000000000004"  # Shadow, admission student_disputed
SHADOW = "10000000-0000-4000-8000-000000000003"


def test_disputed_admission_is_409_in_fixture_mode(client):
    r = client.get(f"/certificates/{DISPUTED}", params={"format": "pdf"}, headers=AICTE)
    assert r.status_code == 409
    assert r.json()["detail"] == {
        "code": "ADMISSION_DISPUTED",
        "message": "This admission is disputed by the student and under review",
    }
    other = client.get(f"/certificates/{DISPUTED}", headers=as_role("institution_admin", MEGHDOOT))
    assert other.status_code == 403
    own = client.get(f"/certificates/{DISPUTED}", headers=as_role("institution_admin", SHADOW))
    assert own.status_code == 409


def test_disputed_admission_is_409_in_real_mode(client, real_db):
    real_db.admission = {**ADMISSION, "status": "student_disputed"}
    r = client.get("/students/me/certificate", headers=as_role("student"))
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ADMISSION_DISPUTED"
    assert real_db.credentials == {}
    assert real_db.events == []
    assert not any("insert into" in sql for sql, _ in real_db.calls)
