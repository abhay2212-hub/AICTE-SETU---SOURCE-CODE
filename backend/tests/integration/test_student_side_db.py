# Owner: Dev B
"""Task 03 flows against Postgres: cross-institution Blind Match, the student portal API,
credentials, the edit-request queue and the integrity results table.

Run: RUN_DB_TESTS=1 uv run pytest tests/integration -q
Only TEST- institutions and this run's students are touched; nothing here rescans or
re-encodes the rest of the database.
"""

from __future__ import annotations

import base64
import json

import pytest

from app.core.db import transaction
from app.services import blind_match, credentials, integrity_store
from tests.integration.conftest import AICTE, as_institution
from tests.integration.test_pipeline_db import commit, rows_for, to_csv, upload

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def secrets_set(db_settings):
    """Blind Match and credential keys for this module, restored afterwards."""
    saved = (db_settings.blind_match_secret, db_settings.credential_signing_key)
    db_settings.blind_match_secret = saved[0] or "integration-blind-match-secret"
    db_settings.credential_signing_key = saved[1] or credentials.TEST_SEED_HEX
    yield db_settings
    db_settings.blind_match_secret, db_settings.credential_signing_key = saved


@pytest.fixture(scope="module")
def pair(world, secrets_set):
    """The same person committed at A and at B: name typed differently, different APAAR."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    a, b, run = world["a"], world["b"], world["run"]
    common = {
        "dob": "2001-04-17",
        "guardian_name": f"Harbhajan Testpair {run}",
        "category": "general",
        "gender": "male",
    }
    first = rows_for(world, a, "UG-CSE", 1, start=7001, student_name=f"Gurpreet Testpair {run}")
    second = rows_for(world, b, "UG-CSE", 1, start=7002, student_name=f"Gurpret Testpair {run}")
    for row in (*first, *second):
        row.update(common)
    ids = []
    for inst, rows in ((a, first), (b, second)):
        batch = upload(client, inst, to_csv(rows)).json()["batch"]
        assert batch["status"] == "validated", batch
        result = commit(client, inst, batch["id"])
        assert result.status_code == 200 and result.json()["rows_committed"] == 1, result.text
        with transaction() as conn:
            row = conn.execute(
                "select id, bloom_identity is not null as encoded, bloom_block"
                " from public.students where apaar_id = %s",
                (rows[0]["apaar_id"],),
            ).fetchone()
        assert row["encoded"] and row["bloom_block"]
        ids.append(str(row["id"]))
    yield {"client": client, "students": ids, "rows": (first[0], second[0])}
    with transaction() as conn:
        conn.execute(
            "delete from public.credential_revocations where student_id = any(%s::uuid[])", (ids,)
        )


def _cases_for(client, ids, headers=AICTE):
    """Listed cases about this pair; an institution user sees one side as HIDDEN."""
    ids = set(ids)
    out = []
    for case in client.get("/blind-match/cases", headers=headers).json():
        records = {case["record_a"], case["record_b"]}
        if records & ids and records - {blind_match.HIDDEN} <= ids:
            out.append(case)
    return out


# ---------------------------------------------------------------------------- Blind Match
def test_cross_institution_pair_with_different_apaar_opens_one_case(pair, world):
    client, ids = pair["client"], pair["students"]
    key = blind_match.pair_key(*ids)
    with transaction() as conn:
        cases = conn.execute(
            "select id, institution_id, evidence from public.review_cases"
            " where kind = 'blind_match' and evidence->>'pair_key' = %s",
            (key,),
        ).fetchall()
    assert len(cases) == 1
    evidence = cases[0]["evidence"]
    assert {evidence["institution_a_id"], evidence["institution_b_id"]} == {
        world["a"]["id"],
        world["b"]["id"],
    }
    assert str(cases[0]["institution_id"]) == world["b"]["id"]
    assert evidence["dice"] >= 0.85 and evidence["matched_on"] == ["name", "dob", "guardian"]
    text = json.dumps(evidence)
    for raw in ("Gurpre", "Harbhajan", "2001-04-17", *(r["apaar_id"] for r in pair["rows"])):
        assert raw not in text

    listed = _cases_for(client, ids)
    assert len(listed) == 1
    assert listed[0]["identity_hint_a"] and listed[0]["institution_a_name"]
    assert listed[0]["status"] == "open"


def test_rescan_adds_no_case(pair):
    ids = pair["students"]
    with transaction() as conn:
        created, events = blind_match.match_students(conn, ids)
        again, _ = blind_match.match_students(conn, list(reversed(ids)))
        count = conn.execute(
            "select count(*) as n from public.review_cases"
            " where kind = 'blind_match' and evidence->>'pair_key' = %s",
            (blind_match.pair_key(*ids),),
        ).fetchone()["n"]
    assert (created, events, again, count) == ([], [], [], 1)


def test_institution_sees_only_own_side(pair, world):
    client = pair["client"]
    a_view = _cases_for(client, pair["students"], as_institution(world["a"]))
    assert len(a_view) == 1
    case = a_view[0]
    own = "a" if case["institution_a_id"] == world["a"]["id"] else "b"
    other = "b" if own == "a" else "a"
    assert case[f"institution_{other}_id"] == blind_match.HIDDEN
    assert case[f"record_{other}"] == blind_match.HIDDEN
    assert case[f"institution_{other}_name"] is None
    assert case["identity_hint_a"] is None and case["identity_hint_b"] is None


def test_review_case_list_scopes_blind_match_to_case_institution(pair, world):
    client = pair["client"]
    cases = client.get(
        "/review-cases", params={"kind": "blind_match"}, headers=as_institution(world["b"])
    ).json()
    assert any(c["evidence"]["pair_key"] == blind_match.pair_key(*pair["students"]) for c in cases)


# ---------------------------------------------------------------------------- student portal
def as_student(student_id):
    return {"X-Demo-Role": "student", "X-Demo-Student": student_id}


def test_portal_response_changes_status_and_opens_dispute(pair):
    client, me, other = pair["client"], *pair["students"]
    records = client.get("/students/me/records", headers=as_student(me)).json()
    assert records["student"]["id"] == me
    assert records["student"]["apaar_id"].startswith("XXXX-XXXX-")
    [admission] = records["admissions"]
    assert admission["status"] == "submitted"

    path = f"/students/me/admissions/{admission['id']}/response"
    response = client.post(path, json={"response": "disputed"}, headers=as_student(me))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "student_disputed" and body["changed"] is True
    assert body["review_case_id"]
    again = client.post(path, json={"response": "disputed"}, headers=as_student(me)).json()
    assert again["changed"] is False and again["review_case_id"] == body["review_case_id"]
    after = client.get("/students/me/records", headers=as_student(me)).json()
    assert after["admissions"][0]["status"] == "student_disputed"

    stolen = client.post(path, json={"response": "confirmed"}, headers=as_student(other))
    assert stolen.status_code == 404


def test_consents_round_trip(pair):
    client, me = pair["client"], pair["students"][0]
    body = {"verifier_id": "ver-test", "purpose": "Test hiring check", "fields": ["programme"]}
    granted = client.post("/students/me/consents", json=body, headers=as_student(me))
    assert granted.status_code == 201, granted.text
    renewed = client.post("/students/me/consents", json=body, headers=as_student(me)).json()
    assert renewed["id"] == granted.json()["id"]
    withdrawn = client.post(
        "/students/me/consents", json=body | {"action": "withdraw"}, headers=as_student(me)
    ).json()
    assert withdrawn["revoked_at"] is not None
    opt_out = client.post(
        "/students/me/consents",
        json={"verifier_id": "-", "purpose": "apaar_sharing", "action": "withdraw"},
        headers=as_student(me),
    ).json()
    assert opt_out["verifier_name"] == "APAAR (SIMULATED)" and opt_out["revoked_at"]
    listed = client.get("/students/me/consents", headers=as_student(me)).json()
    assert {c["purpose"] for c in listed} == {"Test hiring check", "apaar_sharing"}


def test_credential_issue_verify_revoke(pair):
    client, me, other = pair["client"], *pair["students"]
    issued = client.post(
        "/credentials",
        json={"claims": ["enrolment_status", "programme"], "audience": "Test Verifier Ltd",
              "expiry": "15m"},
        headers=as_student(me),
    )  # fmt: skip
    assert issued.status_code == 201, issued.text
    cred = issued.json()
    raw = base64.urlsafe_b64decode(cred["qr_text"] + "=" * (-len(cred["qr_text"]) % 4))
    assert pair["rows"][0]["apaar_id"] not in raw.decode()

    ok = client.post("/credentials/verify", json={"qr_text": cred["qr_text"]}).json()
    assert ok["valid"] is True and ok["claims"] == cred["claims"]

    stolen = client.post(
        f"/credentials/{cred['id']}/revoke", json={"reason": "x"}, headers=as_student(other)
    )
    assert stolen.status_code == 404
    revoked = client.post(
        f"/credentials/{cred['id']}/revoke", json={"reason": "Lost phone"}, headers=as_student(me)
    )
    assert revoked.status_code == 200, revoked.text
    listed = client.get("/credentials/revocations").json()["revoked"]
    assert any(r["credential_id"] == cred["id"] for r in listed)
    failed = client.post("/credentials/verify", json={"qr_text": cred["qr_text"]}).json()
    assert failed == {"valid": False, "reason": "revoked", "expires_at": ok["expires_at"]}

    log = client.get("/students/me/access-log", headers=as_student(me)).json()
    purposes = [e["purpose"] for e in log]
    assert purposes[:3] == [
        "credential verification",
        "credential verification",
        "credential issued for Test Verifier Ltd",
    ]
    assert log[0]["accessor"] == "Test Verifier Ltd" and log[0]["accessor_role"] == "verifier"


def test_public_key_matches_signing_key(pair, secrets_set):
    key = pair["client"].get("/credentials/public-key").json()
    expected = credentials.signing_key(secrets_set.credential_signing_key)
    assert key["public_key_b64"] == credentials.public_key_b64(expected)


# ---------------------------------------------------------------------------- edit requests
def test_edit_request_queue_filters_and_scoping(pair, world):
    client, a, b = pair["client"], world["a"], world["b"]
    records = client.get("/students/me/records", headers=as_student(pair["students"][1])).json()
    admission_id = records["admissions"][0]["id"]
    created = client.post(
        f"/admissions/{admission_id}/edit-requests",
        json={"field": "qualifying_exam_pct", "new_value": "81", "reason": "Typo in marks"},
        headers=as_institution(b),
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]

    mine = client.get(
        "/edit-requests", params={"status": "pending"}, headers=as_institution(b)
    ).json()
    found = next(r for r in mine if r["id"] == request_id)
    assert found["institution_id"] == b["id"]
    assert found["admission"]["id"] == admission_id
    assert found["admission"]["apaar_id_masked"].startswith("XXXX-XXXX-")
    assert all(r["institution_id"] == b["id"] for r in mine)
    assert not any(
        r["id"] == request_id
        for r in client.get("/edit-requests", headers=as_institution(a)).json()
    )
    everyone = client.get(
        "/edit-requests", params={"institution_id": b["id"], "academic_year": "2026-27"},
        headers={"X-Demo-Role": "auditor"},
    ).json()  # fmt: skip
    assert any(r["id"] == request_id for r in everyone)
    none = client.get(
        "/edit-requests", params={"institution_id": b["id"], "status": "approved"}, headers=AICTE
    ).json()
    assert not any(r["id"] == request_id for r in none)
    stamps = [r["created_at"] for r in everyone]
    assert stamps == sorted(stamps, reverse=True)


# ---------------------------------------------------------------------------- integrity
def test_integrity_results_upsert_and_latest(world):
    inst = world["a"]["id"]
    result = {
        "institution_id": inst,
        "academic_year": "2026-27",
        "score": 41.5,
        "tier": "watch",
        "model_version": "test-0",
        "components": {"anomaly": 0.5},
        "top_features": [{"feature": "cap_filling", "value": 1.1}],
        "signals": [{"code": "INTAKE_OVERRUN", "count": 1}],
    }
    with transaction() as conn:
        assert integrity_store.save_results(conn, [result]) == 1
        assert integrity_store.save_results(conn, [result | {"score": 55, "tier": "high"}]) == 1
        latest = integrity_store.latest_for(conn, inst, "2026-27")
        rows = conn.execute(
            "select count(*) as n from public.integrity_scores where institution_id = %s",
            (inst,),
        ).fetchone()["n"]
        conn.execute("delete from public.integrity_scores where institution_id = %s", (inst,))
    assert rows == 1
    assert (latest["score"], latest["tier"]) == (55.0, "high")
    assert latest["components"] == {"anomaly": 0.5}


def test_compute_integrity_for_test_institution(world):
    from app.services.integrity import compute_and_save_integrity, compute_institution_results

    inst_id = world["a"]["id"]
    with transaction() as conn:
        results = compute_institution_results(
            conn, academic_year="2026-27", institution_ids=[inst_id]
        )
        assert len(results) == 1
        res = results[0]
        assert res["institution_id"] == inst_id
        assert res["academic_year"] == "2026-27"
        assert 0.0 <= res["score"] <= 100.0
        assert "components" in res

        saved = compute_and_save_integrity(conn, results=results, academic_year="2026-27")
        assert saved == 1

        latest = integrity_store.latest_for(conn, inst_id, "2026-27")
        assert latest is not None
        assert latest["score"] == res["score"]
        conn.execute("delete from public.integrity_scores where institution_id = %s", (inst_id,))
