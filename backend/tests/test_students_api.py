# Owner: Dev B
"""Student endpoints and the edit-request queue in fixture mode, plus demo-student rules."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.auth import User
from app.services import students as service
from tests.conftest import as_role

ME = "40000000-0000-4000-8000-000000000001"
OTHER = "40000000-0000-4000-8000-000000000002"
MY_ADMISSION = "50000000-0000-4000-8000-000000000001"
OTHER_ADMISSION = "50000000-0000-4000-8000-000000000002"
MEGHDOOT = "10000000-0000-4000-8000-000000000001"
SHADOW = "10000000-0000-4000-8000-000000000003"


def student(demo_student: str | None = None) -> dict[str, str]:
    headers = as_role("student")
    if demo_student:
        headers["X-Demo-Student"] = demo_student
    return headers


def test_records_are_the_demo_students_own_with_apaar_masked(client):
    body = client.get("/students/me/records", headers=student()).json()
    assert body["student"]["id"] == ME
    assert body["student"]["apaar_id"] == "XXXX-XXXX-0001"
    assert body["student"]["apaar_id_masked"] == "XXXX-XXXX-0001"
    assert {a["student_id"] for a in body["admissions"]} == {ME}
    assert "999912340001" not in str(body)


def test_x_demo_student_switches_student(client):
    body = client.get("/students/me/records", headers=student(OTHER)).json()
    assert body["student"]["id"] == OTHER
    assert {a["student_id"] for a in body["admissions"]} == {OTHER}


def test_student_responds_only_to_own_admission(client):
    path = "/students/me/admissions/{}/response"
    ok = client.post(path.format(MY_ADMISSION), json={"response": "disputed"}, headers=student())
    assert ok.status_code == 200 and ok.json()["status"] == "student_disputed"
    other = client.post(
        path.format(OTHER_ADMISSION), json={"response": "confirmed"}, headers=student()
    )
    assert other.status_code == 404
    bad = client.post(path.format(MY_ADMISSION), json={"response": "maybe"}, headers=student())
    assert bad.status_code == 422
    admin = client.post(
        path.format(MY_ADMISSION), json={"response": "confirmed"}, headers=as_role("aicte_admin")
    )
    assert admin.status_code == 403


def test_consent_grant_withdraw_and_apaar_opt_out(client):
    body = {
        "verifier_id": "ver-acme-infotech",
        "purpose": "Campus hiring background check",
        "fields": ["programme"],
    }
    granted = client.post("/students/me/consents", json=body, headers=student())
    assert granted.status_code == 201 and granted.json()["revoked_at"] is None
    withdrawn = client.post(
        "/students/me/consents", json=body | {"action": "withdraw"}, headers=student()
    ).json()
    assert withdrawn["revoked_at"] is not None
    opt_out = client.post(
        "/students/me/consents",
        json={"verifier_id": "x", "purpose": "apaar_sharing", "action": "withdraw"},
        headers=student(),
    ).json()
    assert (opt_out["verifier_id"], opt_out["verifier_name"]) == service.APAAR_VERIFIER
    assert opt_out["revoked_at"] is not None


def test_access_log_newest_first(client):
    entries = client.get("/students/me/access-log", headers=student()).json()
    times = [e["accessed_at"] for e in entries]
    assert times == sorted(times, reverse=True)


def test_fixture_student_id_rules():
    demo = User(id="demo-student", role="student", demo=True)
    assert service.fixture_student_id(demo, None) == service.FIXTURE_STUDENT
    assert service.fixture_student_id(demo, OTHER) == OTHER
    linked = User(id="auth-user", role="student", student_id=OTHER)
    assert service.fixture_student_id(linked, ME) == OTHER  # header ignored outside MOCK_MODE
    with pytest.raises(HTTPException) as err:
        service.fixture_student_id(User(id="auth-user", role="student"), None)
    assert err.value.status_code == 403


# ---------------------------------------------------------------------------- edit requests
def test_edit_requests_list_with_masked_admission(client):
    rows = client.get("/edit-requests", headers=as_role("aicte_admin")).json()
    assert rows and rows[0]["admission"]["apaar_id_masked"].startswith("XXXX-XXXX-")
    assert rows[0]["institution_id"] == SHADOW


def test_edit_requests_filters(client):
    def count(**params):
        return len(client.get("/edit-requests", params=params, headers=as_role("auditor")).json())

    assert count(status="pending") == 1
    assert count(status="approved") == 0
    assert count(academic_year="2026-27") == 1
    assert count(academic_year="2025-26") == 0
    assert count(institution_id=MEGHDOOT) == 0
    assert count(limit=1, offset=1) == 0
    bad = client.get("/edit-requests", params={"limit": 201}, headers=as_role("auditor"))
    assert bad.status_code == 422


def test_edit_requests_institution_scoping(client):
    own = client.get("/edit-requests", headers=as_role("institution_operator", SHADOW)).json()
    assert len(own) == 1
    elsewhere = client.get("/edit-requests", headers=as_role("institution_admin", MEGHDOOT))
    assert elsewhere.json() == []
    forbidden = client.get(
        "/edit-requests",
        params={"institution_id": SHADOW},
        headers=as_role("institution_admin", MEGHDOOT),
    )
    assert forbidden.status_code == 403
    assert client.get("/edit-requests", headers=as_role("student")).status_code == 403
