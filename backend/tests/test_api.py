# Owner: Dev B
import pytest

from tests.conftest import as_role

SHADOW = "10000000-0000-4000-8000-000000000003"
STUDENT = "40000000-0000-4000-8000-000000000001"
BATCH = "30000000-0000-4000-8000-000000000001"
CASE = "60000000-0000-4000-8000-000000000001"

# Every GET endpoint, with a role allowed to call it.
GET_ENDPOINTS = [
    ("/health", "aicte_admin"),
    ("/public/stats", "student"),
    ("/engine", "aicte_admin"),
    ("/engine/health", "aicte_admin"),
    ("/me", "aicte_admin"),
    ("/institutions", "aicte_admin"),
    (f"/institutions/{SHADOW}", "aicte_admin"),
    (f"/institutions/{SHADOW}/seat-ledger?academic_year=2026-27", "institution_admin"),
    ("/batches", "aicte_admin"),
    (f"/batches/{BATCH}", "institution_operator"),
    (f"/batches/{BATCH}/issues", "institution_operator"),
    ("/admissions", "aicte_admin"),
    ("/review-cases", "aicte_admin"),
    (f"/review-cases/{CASE}", "aicte_admin"),
    ("/audit/verify", "auditor"),
    ("/submission-windows", "institution_operator"),
    ("/integrity/institutions", "aicte_admin"),
    (f"/integrity/institutions/{SHADOW}", "aicte_admin"),
    ("/blind-match/cases", "aicte_admin"),
    ("/reports/enrolment?group_by=state&format=json", "aicte_admin"),
    ("/reports/states", "aicte_admin"),
    (f"/reports/accreditation/{SHADOW}?format=json", "aicte_admin"),
    (f"/certificates/{STUDENT}", "student"),
    ("/credentials/revocations", "verifier"),
    ("/credentials/public-key", "verifier"),
    ("/students/me/records", "student"),
    ("/students/me/certificate", "student"),
    ("/students/me/consents", "student"),
    ("/students/me/access-log", "student"),
    ("/edit-requests", "aicte_admin"),
    ("/edit-requests/fields", "aicte_admin"),
]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True
    assert body["engine_import_ok"] is True
    assert response.headers["X-Mock"] == "true"


def test_me_uses_demo_headers(client):
    response = client.get("/me", headers=as_role("institution_admin", SHADOW))
    assert response.status_code == 200
    assert response.json()["role"] == "institution_admin"
    assert response.json()["institution_id"] == SHADOW


def test_me_defaults_to_aicte_admin(client):
    assert client.get("/me").json()["role"] == "aicte_admin"


def test_unknown_demo_role_rejected(client):
    assert client.get("/me", headers=as_role("superuser")).status_code == 400


def test_role_guard_returns_403(client):
    assert client.get("/audit/verify", headers=as_role("student")).status_code == 403
    assert client.get("/students/me/records", headers=as_role("aicte_admin")).status_code == 403


@pytest.mark.parametrize(("path", "role"), GET_ENDPOINTS)
def test_get_endpoints_return_200_in_mock_mode(client, path, role):
    response = client.get(path, headers=as_role(role))
    assert response.status_code == 200, response.text


def test_every_get_route_is_covered():
    from app.main import app

    routes = {path for path, ops in app.openapi()["paths"].items() if "get" in ops}
    covered = {p.split("?")[0] for p, _ in GET_ENDPOINTS}
    placeholders = {
        "/institutions/{institution_id}": f"/institutions/{SHADOW}",
        "/institutions/{institution_id}/seat-ledger": f"/institutions/{SHADOW}/seat-ledger",
        "/batches/{batch_id}": f"/batches/{BATCH}",
        "/batches/{batch_id}/issues": f"/batches/{BATCH}/issues",
        "/review-cases/{case_id}": f"/review-cases/{CASE}",
        "/integrity/institutions/{institution_id}": f"/integrity/institutions/{SHADOW}",
        "/reports/accreditation/{institution_id}": f"/reports/accreditation/{SHADOW}",
        "/certificates/{student_id}": f"/certificates/{STUDENT}",
    }
    assert {placeholders.get(r, r) for r in routes} == covered


def test_admissions_apaar_masked(client):
    for row in client.get("/admissions").json():
        masked = row["apaar_id_masked"]
        assert masked is None or (masked.startswith("XXXX-XXXX-") and len(masked) == 14)


def test_shadow_overrun_in_seat_ledger(client):
    ledger = client.get(f"/institutions/{SHADOW}/seat-ledger").json()
    cse = next(p for p in ledger["programmes"] if p["programme_code"] == "UG-CSE")
    assert (cse["approved_total"], cse["admitted_total"]) == (60, 71)


def test_batch_issues_cover_eight_rule_codes(client):
    issues = client.get(f"/batches/{BATCH}/issues").json()
    assert len({i["rule_code"] for i in issues}) >= 8


def test_resolve_requires_note(client):
    path = f"/review-cases/{CASE}/resolve"
    assert client.post(path, json={"status": "confirmed"}).status_code == 422
    ok = client.post(path, json={"status": "confirmed", "note": "Checked approval letter."})
    assert ok.status_code == 200
    assert ok.json()["reviewer_note"] == "Checked approval letter."


def test_reports_files(client):
    pdf = client.get("/reports/enrolment?group_by=programme&format=pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xlsx = client.get("/reports/enrolment?group_by=gender&format=xlsx")
    assert xlsx.status_code == 200 and xlsx.content.startswith(b"PK")


def test_batch_upload_suggests_mapping(client):
    csv = b"Student Name,DOB,APAAR ID,Seat Pool,Unknown Column\n"
    response = client.post(
        "/batches",
        files={"file": ("admissions.csv", csv, "text/csv")},
        headers=as_role("institution_admin", SHADOW),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["suggested_mapping"]["Student Name"] == "student_name"
    assert body["suggested_mapping"]["APAAR ID"] == "apaar_id"
    assert "Unknown Column" in body["unmapped_columns"]


def test_apaar_verify_is_simulated(client):
    body = client.post("/integrations/apaar/verify", json={"apaar_id": "999912340001"}).json()
    assert body["simulated"] is True
    assert body["result"] == "found"
    assert body["apaar_id_masked"] == "XXXX-XXXX-0001"


def test_credential_signature_verifies(client):
    import base64
    import json

    from nacl.signing import VerifyKey

    from app.services.credentials import canonical_bytes

    key = client.get("/credentials/public-key").json()
    cred = client.post(
        "/credentials",
        json={"claims": ["programme"], "audience": "Acme Infotech", "expiry": "1d"},
        headers=as_role("student"),
    ).json()
    text = cred["qr_text"]
    envelope = json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))
    verify_key = VerifyKey(base64.b64decode(key["public_key_b64"]))
    verify_key.verify(canonical_bytes(envelope["payload"]), base64.b64decode(envelope["sig"]))


def test_webhook_checks_secret(client, settings_override):
    settings_override(telegram_webhook_secret="s3cret")
    update = {"message": {"text": "/start abc"}}
    assert client.post("/webhooks/telegram", json=update).status_code == 401
    ok = client.post(
        "/webhooks/telegram", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    )
    assert ok.status_code == 200 and ok.json()["handled"] == "start"


def test_outside_mock_mode_needs_jwt_then_falls_back_to_fixtures(client, settings_override):
    import jwt

    settings_override(mock_mode=False, supabase_jwt_secret="test-secret-at-least-32-bytes-long!!")
    bad = client.get("/review-cases", headers={"Authorization": "Bearer bad"})
    assert bad.status_code == 401

    token = jwt.encode(
        {"sub": "u1", "aud": "authenticated", "app_metadata": {"role": "aicte_admin"}},
        "test-secret-at-least-32-bytes-long!!",
        algorithm="HS256",
    )
    response = client.get("/review-cases", headers={"Authorization": f"Bearer {token}"})
    # MOCK_MODE only controls auth now; a domain not in REAL_DOMAINS still serves fixtures.
    assert response.status_code == 200
    assert response.headers["X-Mock"] == "true"
