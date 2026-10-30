# Owner: Dev B
"""Task 02 flows against Postgres: submission windows and lock, withdrawals, corrections,
student responses and API-key uploads. Run: RUN_DB_TESTS=1 uv run pytest tests/integration"""

from __future__ import annotations

import pytest

from app.core.db import transaction
from tests.integration.conftest import AICTE, TEST_YEARS, as_institution
from tests.integration.test_pipeline_db import commit, rows_for, to_csv, upload

pytestmark = pytest.mark.db

TOKEN = "integration-internal-token"


@pytest.fixture
def internal(db_settings):
    saved = db_settings.internal_api_token
    db_settings.internal_api_token = TOKEN
    yield {"X-Internal-Token": TOKEN}
    db_settings.internal_api_token = saved


def committed_admissions(client, inst, batch_id, **params):
    rows = client.get(
        "/admissions",
        params={"institution_id": inst["id"], "limit": 200, **params},
        headers=AICTE,
    ).json()
    return [a for a in rows if a["batch_id"] == batch_id]


def set_window(client, year, opens, closes):
    body = {"academic_year": year, "opens_at": opens, "closes_at": closes}
    response = client.post("/submission-windows", json=body, headers=AICTE)
    assert response.status_code == 201, response.text
    return response.json()


def ledger_pool(client, inst, programme, pool, year="2026-27"):
    ledger = client.get(
        f"/institutions/{inst['id']}/seat-ledger",
        params={"academic_year": year},
        headers=AICTE,
    ).json()
    entry = next(p for p in ledger["programmes"] if p["programme_code"] == programme)
    return next(p for p in entry["pools"] if p["pool"] == pool)


# ---------------------------------------------------------------------------- windows
def test_closed_window_rejects_upload_and_commit(client, world):
    a, year = world["a"], TEST_YEARS[1]
    window = set_window(client, year, "2020-01-01T00:00:00Z", "2099-12-31T00:00:00Z")
    assert window["state"] == "open"
    rows = rows_for(world, a, "UG-IT", 2, start=2001, academic_year=year)
    batch = upload(client, a, to_csv(rows)).json()["batch"]
    assert batch["status"] == "validated"

    locked = client.post(f"/submission-windows/{window['id']}/lock", headers=AICTE)
    assert locked.status_code == 200 and locked.json()["state"] == "locked"
    listed = client.get("/submission-windows", headers=as_institution(a)).json()
    assert next(w for w in listed if w["academic_year"] == year)["state"] == "locked"

    refused = commit(client, a, batch["id"])
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "SUBMISSION_WINDOW_CLOSED"
    again = upload(
        client, a, to_csv(rows_for(world, a, "UG-IT", 1, start=2011, academic_year=year))
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "SUBMISSION_WINDOW_CLOSED"
    # A locked window cannot be moved, and only aicte_admin sets windows.
    moved = client.post(
        "/submission-windows",
        json={"academic_year": year, "opens_at": "2020-01-01T00:00:00Z",
              "closes_at": "2100-01-01T00:00:00Z"},
        headers=AICTE,
    )  # fmt: skip
    assert moved.status_code == 409
    denied = client.post(f"/submission-windows/{window['id']}/lock", headers=as_institution(a))
    assert denied.status_code == 403


def test_post_lock_edit_requests_approve_and_reject(client, world):
    a, year = world["a"], TEST_YEARS[0]
    window = set_window(client, year, "2020-01-01T00:00:00Z", "2099-12-31T00:00:00Z")
    rows = rows_for(world, a, "UG-CE", 3, start=2101, academic_year=year)
    batch_id = upload(client, a, to_csv(rows)).json()["batch"]["id"]
    assert commit(client, a, batch_id).status_code == 200
    first, second, third = committed_admissions(client, a, batch_id, academic_year=year)
    assert client.post(f"/submission-windows/{window['id']}/lock", headers=AICTE).status_code == 200

    # After the lock, a direct withdrawal is refused...
    direct = client.post(
        f"/admissions/{first['id']}/withdraw", json={"reason": "Left"}, headers=as_institution(a)
    )
    assert direct.status_code == 409
    assert direct.json()["detail"]["code"] == "SUBMISSION_WINDOW_CLOSED"

    # ...and goes through an edit request instead. Approving it withdraws the admission.
    def request(admission, field, value):
        response = client.post(
            f"/admissions/{admission['id']}/edit-requests",
            json={"field": field, "new_value": value, "reason": "Found after the lock."},
            headers=as_institution(a),
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    before = ledger_pool(client, a, "UG-CE", "regular", year)["admitted"]
    withdrawal = request(first, "withdrawal", "withdrawn")
    approved = client.post(
        f"/edit-requests/{withdrawal}/decision",
        json={"decision": "approved", "note": "Withdrawal letter seen."},
        headers=AICTE,
    )
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    withdrawn = committed_admissions(client, a, batch_id, status="withdrawn")
    assert [x["id"] for x in withdrawn] == [first["id"]]
    assert ledger_pool(client, a, "UG-CE", "regular", year)["admitted"] == before - 1

    date_fix = request(second, "admission_date", "2026-08-01")
    approved = client.post(
        f"/edit-requests/{date_fix}/decision", json={"decision": "approved"}, headers=AICTE
    )
    assert approved.status_code == 200
    rejected_id = request(third, "admission_date", "2026-08-02")
    rejected = client.post(
        f"/edit-requests/{rejected_id}/decision",
        json={"decision": "rejected", "note": "No supporting document."},
        headers=AICTE,
    )
    assert rejected.status_code == 200 and rejected.json()["status"] == "rejected"
    dates = {
        x["id"]: x["admission_date"]
        for x in committed_admissions(client, a, batch_id, academic_year=year)
    }
    assert dates[second["id"]] == "2026-08-01" and dates[third["id"]] == "2026-08-05"
    assert (
        client.post(
            f"/edit-requests/{rejected_id}/decision", json={"decision": "approved"}, headers=AICTE
        ).status_code
        == 409
    )

    decided = {
        r["id"]: r
        for r in client.get(
            "/edit-requests", params={"institution_id": a["id"]}, headers=AICTE
        ).json()
    }
    with transaction() as conn:
        actions = {
            r["action"]
            for r in conn.execute(
                "select action from public.audit_events where entity_id = any(%s)",
                ([withdrawal, date_fix, rejected_id, first["id"], window["id"]],),
            ).fetchall()
        }
        deciders = {
            r["entity_id"]: r["actor"]
            for r in conn.execute(
                "select entity_id, actor from public.audit_events"
                " where action in ('edit_request.approved', 'edit_request.rejected')"
                " and entity_id = any(%s)",
                ([withdrawal, date_fix, rejected_id],),
            ).fetchall()
        }
    for request_id in (withdrawal, date_fix, rejected_id):
        assert decided[request_id]["decided_by"] == deciders[request_id] == "demo-aicte_admin"
    assert {
        "edit_request.approved",
        "edit_request.rejected",
        "admission.withdrawn",
        "submission_window.locked",
    } <= actions


# ---------------------------------------------------------------------------- withdrawals
def test_withdraw_releases_a_seat_and_notes_the_overrun_case(client, world):
    b = world["b"]
    batch_id = upload(client, b, to_csv(rows_for(world, b, "UG-CE", 61, start=3001))).json()[
        "batch"
    ]["id"]
    result = commit(client, b, batch_id).json()
    assert result["rows_committed"] == 61
    assert ledger_pool(client, b, "UG-CE", "regular")["overrun"] == 1
    case = next(
        c
        for c in client.get("/review-cases?kind=intake_overrun", headers=AICTE).json()
        if c["institution_id"] == b["id"] and c["evidence"]["programme"] == "UG-CE"
    )

    target = committed_admissions(client, b, batch_id)[0]
    path = f"/admissions/{target['id']}/withdraw"
    assert (
        client.post(
            path, json={"reason": "x"}, headers=as_institution(b, "institution_operator")
        ).status_code
        == 403
    )
    response = client.post(
        path, json={"reason": "Joined another college."}, headers=as_institution(b)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "withdrawn"
    pool = ledger_pool(client, b, "UG-CE", "regular")
    assert (pool["admitted"], pool["overrun"]) == (60, 0)
    assert client.post(path, json={"reason": "again"}, headers=as_institution(b)).status_code == 409

    with transaction() as conn:
        stored = conn.execute(
            "select status::text as status, notes from public.review_cases where id = %s",
            (case["id"],),
        ).fetchone()
    assert stored["status"] == "open"  # noted, never auto-closed
    assert len(stored["notes"]) == 1 and "back within capacity" in stored["notes"][0]["text"]


# ---------------------------------------------------------------------------- corrections
def test_corrections_commit_only_the_fixed_rows(client, world):
    a = world["a"]
    rows = rows_for(world, a, "UG-IT", 5, start=4001)
    rows[1]["apaar_id"] = "123"  # APAAR_FORMAT
    rows[3]["admission_date"] = "2026-02-30"  # DATE_INVALID
    batch = upload(client, a, to_csv(rows)).json()["batch"]
    first = commit(client, a, batch["id"]).json()
    assert (first["rows_committed"], first["rows_rejected"]) == (3, 2)

    fixed = rows_for(world, a, "UG-IT", 5, start=4001)
    # Both rejected rows fixed, plus one row that was never rejected and one stranger.
    correction = [fixed[1], fixed[3], fixed[0], rows_for(world, a, "UG-IT", 1, start=4099)[0]]
    path = f"/batches/{batch['id']}/corrections"
    files = {"file": ("fix.csv", to_csv(correction), "text/csv")}
    response = client.post(path, files=files, headers=as_institution(a))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["parent_batch_id"] == batch["id"]
    assert (result["rows_committed"], result["rows_not_matched"]) == (2, 2)

    mine = committed_admissions(client, a, batch["id"]) + committed_admissions(
        client, a, result["batch_id"]
    )
    assert len(mine) == 5
    issues = client.get(f"/batches/{batch['id']}/issues", headers=as_institution(a)).json()
    errors = [i for i in issues if i["severity"] == "error"]
    assert errors and all(i["resolved"] for i in errors)
    child = client.get(f"/batches/{result['batch_id']}", headers=as_institution(a)).json()
    assert child["parent_batch_id"] == batch["id"]

    again = client.post(path, files=files, headers=as_institution(a))
    assert again.status_code == 200 and again.json() == result
    other = to_csv(rows_for(world, a, "UG-IT", 1, start=4098))
    nothing_left = client.post(
        path, files={"file": ("fix2.csv", other, "text/csv")}, headers=as_institution(a)
    )
    assert nothing_left.status_code == 409


def test_resolve_validation_issue(client, world):
    a = world["a"]
    rows = rows_for(world, a, "UG-IT", 1, start=4201, admission_date="2026-10-02")
    batch = upload(client, a, to_csv(rows)).json()["batch"]
    issues = client.get(f"/batches/{batch['id']}/issues", headers=as_institution(a)).json()
    late = next(i for i in issues if i["rule_code"] == "ADMISSION_AFTER_CUTOFF")
    path = f"/validation-issues/{late['id']}/resolve"
    ok = client.post(path, json={"note": "Late CAP round."}, headers=as_institution(a))
    assert ok.status_code == 200, ok.text
    assert ok.json()["resolved"] and ok.json()["resolution_note"] == "Late CAP round."
    assert (
        client.post(path, json={"note": "x"}, headers=as_institution(world["b"])).status_code == 403
    )


# ---------------------------------------------------------------------------- student responses
def test_dispute_opens_a_case_and_repeats_are_no_ops(client, world, internal):
    a = world["a"]
    batch_id = upload(client, a, to_csv(rows_for(world, a, "UG-IT", 2, start=5001))).json()[
        "batch"
    ]["id"]
    commit(client, a, batch_id)
    disputed_one, confirmed_one = committed_admissions(client, a, batch_id)

    def respond(admission, response, channel="telegram"):
        return client.post(
            "/internal/student-responses",
            json={"admission_id": admission["id"], "response": response, "channel": channel},
            headers=internal,
        )

    first = respond(disputed_one, "disputed")
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "student_disputed" and body["changed"] is True
    case = client.get(f"/review-cases/{body['review_case_id']}", headers=AICTE).json()
    assert case["kind"] == "dispute" and case["status"] == "open"
    assert case["evidence"] == {
        "admission_id": disputed_one["id"],
        "institution_id": a["id"],
        "programme": "UG-IT",
        "academic_year": "2026-27",
        "channel": "telegram",
    }

    with transaction() as conn:
        audit_before = conn.execute("select count(*) as n from public.audit_events").fetchone()["n"]
    repeat = respond(disputed_one, "disputed", "portal")
    assert repeat.status_code == 200
    assert repeat.json() == {**body, "changed": False}
    with transaction() as conn:
        audit_after = conn.execute("select count(*) as n from public.audit_events").fetchone()["n"]
        disputes = conn.execute(
            "select count(*) as n from public.review_cases where kind = 'dispute'"
            " and evidence->>'admission_id' = %s",
            (disputed_one["id"],),
        ).fetchone()["n"]
    assert audit_after == audit_before and disputes == 1

    confirmed = respond(confirmed_one, "confirmed", "portal")
    assert confirmed.json()["status"] == "student_confirmed"
    assert confirmed.json()["review_case_id"] is None
    assert respond(confirmed_one, "confirmed").json()["changed"] is False
    statuses = {x["id"]: x["status"] for x in committed_admissions(client, a, batch_id)}
    assert statuses == {
        disputed_one["id"]: "student_disputed",
        confirmed_one["id"]: "student_confirmed",
    }
    missing = respond({"id": "00000000-0000-4000-8000-000000000000"}, "confirmed")
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "ADMISSION_NOT_FOUND"
    assert (
        client.post(
            "/internal/student-responses",
            json={
                "admission_id": confirmed_one["id"],
                "response": "confirmed",
                "channel": "portal",
            },
            headers={"X-Internal-Token": "wrong"},
        ).status_code
        == 401
    )


def test_mark_no_response(client, world):
    a = world["a"]
    batch_id = upload(client, a, to_csv(rows_for(world, a, "UG-IT", 2, start=5101))).json()[
        "batch"
    ]["id"]
    commit(client, a, batch_id)
    with transaction() as conn:
        conn.execute(
            "update public.admissions set created_at = now() - interval '30 days'"
            " where batch_id = %s",
            (batch_id,),
        )
    response = client.post(
        "/admin/admissions/mark-no-response", json={"older_than_days": 21}, headers=AICTE
    )
    assert response.status_code == 200 and response.json()["marked"] >= 2
    assert {x["status"] for x in committed_admissions(client, a, batch_id)} == {"no_response"}


# ---------------------------------------------------------------------------- API keys
def test_api_key_upload_is_scoped_and_revocable(client, world):
    a, b = world["a"], world["b"]
    created = client.post(f"/institutions/{a['id']}/api-keys", headers=as_institution(a))
    assert created.status_code == 201
    key = created.json()
    headers = {"X-API-Key": key["api_key"]}

    content = to_csv(rows_for(world, a, "UG-IT", 2, start=6001))
    uploaded = client.post(
        "/batches", files={"file": ("erp.csv", content, "text/csv")}, headers=headers
    )
    assert uploaded.status_code == 201, uploaded.text
    batch = uploaded.json()["batch"]
    assert batch["institution_id"] == a["id"]
    committed = client.post(f"/batches/{batch['id']}/commit", headers=headers)
    assert committed.status_code == 200 and committed.json()["rows_committed"] == 2

    # Scope: the key only acts for its own institution.
    other = upload(client, b, to_csv(rows_for(world, b, "UG-IT", 1, start=6101))).json()
    assert (
        client.post(f"/batches/{other['batch']['id']}/commit", headers=headers).status_code == 403
    )
    rows_for_b = to_csv(rows_for(world, b, "UG-IT", 1, start=6102))
    as_a = client.post(
        "/batches", files={"file": ("b.csv", rows_for_b, "text/csv")}, headers=headers
    )
    issues = client.get(f"/batches/{as_a.json()['batch']['id']}/issues", headers=as_institution(a))
    assert as_a.json()["batch"]["institution_id"] == a["id"]
    assert {i["rule_code"] for i in issues.json()} == {"PROGRAMME_UNKNOWN"}

    with transaction() as conn:
        actors = {
            r["actor"]
            for r in conn.execute(
                "select actor from public.audit_events where entity_id = %s", (batch["id"],)
            ).fetchall()
        }
    assert actors == {f"api_key:{key['key_id']}"}

    revoked = client.post(
        f"/institutions/{a['id']}/api-keys/{key['key_id']}/revoke", headers=as_institution(a)
    )
    assert revoked.status_code == 200 and revoked.json()["revoked_at"]
    denied = client.post(
        "/batches",
        files={
            "file": ("late.csv", to_csv(rows_for(world, a, "UG-IT", 1, start=6201)), "text/csv")
        },
        headers=headers,
    )
    assert denied.status_code == 401
    assert client.post("/batches", files={"file": ("x.csv", content, "text/csv")},
                       headers={"X-API-Key": "apaar_unknown"}).status_code == 401  # fmt: skip
    assert (
        client.post(
            f"/institutions/{b['id']}/api-keys/{key['key_id']}/revoke", headers=as_institution(a)
        ).status_code
        == 403
    )
