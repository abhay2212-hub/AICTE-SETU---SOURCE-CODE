# Owner: Dev B
"""End-to-end pipeline against Postgres. Run: RUN_DB_TESTS=1 uv run pytest tests/integration"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core.db import transaction
from app.services.ingestion import TEMPLATE_COLUMNS
from tests.integration.conftest import AICTE, as_institution

pytestmark = pytest.mark.db
BACKEND = Path(__file__).resolve().parents[2]
FIRST = "Aarav Ananya Arjun Diya Ishaan Kavya Rohan Saanvi Vihaan Zara Kabir Meera".split()
LAST = "Sharma Patel Nair Iyer Gupta Reddy Khan Joshi Rao Singh Das Mehta Verma".split()


def rows_for(world, inst, programme, count, start=1, **overrides):
    """Distinct names and dates of birth per n, so no Blind Match finding appears by accident."""
    rows = []
    for n in range(start, start + count):
        first, last = FIRST[n % len(FIRST)], LAST[(n // len(FIRST)) % len(LAST)]
        dob = date(2007, 1, 1) + timedelta(days=(n * 53) % 900)  # 53 and 900 are coprime
        row = {
            "institution_aicte_code": inst["code"],
            "programme_code": programme,
            "academic_year": "2026-27",
            "student_name": f"{first} {last}",
            "dob": dob.isoformat(),
            "gender": "female" if n % 2 else "male",
            "category": "general",
            "pwd": "false",
            "apaar_id": f"{world['apaar_prefix']}{n:04d}",
            "apaar_opt_out": "false",
            "provisional_id": "",
            "nationality": "IN",
            "oci_status": "false",
            "fn_status": "false",
            "nri_category": "false",
            "seat_pool": "regular",
            "admission_mode": "cap",
            "admission_date": "2026-08-05",
            "qualifying_exam": "JEE Main",
            "qualifying_exam_pct": "80",
            "domicile_state": "Test State",
            "contact_phone": f"+9198{n:08d}",
            "contact_email": f"student{n}@example.com",
            "guardian_name": f"{FIRST[(n * 7) % len(FIRST)]} {last}",
        }
        row.update(overrides)
        rows.append(row)
    return rows


def to_csv(rows, columns=TEMPLATE_COLUMNS, rename=None) -> bytes:
    rename = rename or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([rename.get(c, c) for c in columns])
    for row in rows:
        writer.writerow([row[c] for c in columns])
    return buffer.getvalue().encode()


def upload(client, inst, content, name="admissions.csv"):
    return client.post(
        "/batches",
        files={"file": (name, content, "text/csv")},
        headers=as_institution(inst),
    )


def commit(client, inst, batch_id):
    return client.post(f"/batches/{batch_id}/commit", headers=as_institution(inst))


# ---------------------------------------------------------------------------- happy path
def test_upload_mapping_commit_and_ledger(client, world):
    a = world["a"]
    content = to_csv(rows_for(world, a, "UG-CSE", 5), rename={"student_name": "Pupil"})
    first = upload(client, a, content)
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["batch"]["status"] == "uploaded"
    assert body["missing_required"] == ["student_name"]
    assert "Pupil" in body["unmapped_columns"]
    assert first.headers["X-Mock"] == "false"
    batch_id = body["batch"]["id"]

    mapping = {**body["suggested_mapping"], "Pupil": "student_name"}
    mapped = client.post(
        f"/batches/{batch_id}/mapping", json={"mapping": mapping}, headers=as_institution(a)
    )
    assert mapped.status_code == 200, mapped.text
    assert mapped.json()["status"] == "validated"
    assert mapped.json()["counts"]["errors"] == 0

    result = commit(client, a, batch_id)
    assert result.status_code == 200, result.text
    assert result.json()["rows_committed"] == 5

    ledger = client.get(f"/institutions/{a['id']}/seat-ledger", headers=as_institution(a))
    cse = next(p for p in ledger.json()["programmes"] if p["programme_code"] == "UG-CSE")
    regular = next(p for p in cse["pools"] if p["pool"] == "regular")
    assert (regular["approved_seats"], regular["admitted"], regular["available"]) == (60, 5, 55)

    admissions = client.get(
        "/admissions", params={"institution_id": a["id"], "limit": 200}, headers=AICTE
    ).json()
    mine = [x for x in admissions if x["batch_id"] == batch_id]
    assert len(mine) == 5
    assert all(x["apaar_id_masked"].startswith("XXXX-XXXX-") for x in mine)

    with transaction() as conn:
        stored = conn.execute(
            "select raw::text || normalized::text as t from public.batch_rows where batch_id = %s",
            (batch_id,),
        ).fetchall()
    text = " ".join(r["t"] for r in stored)
    assert "example.com" not in text and "+9198" not in text


def test_idempotent_reupload(client, world):
    a = world["a"]
    content = to_csv(rows_for(world, a, "UG-CSE", 2, start=101))
    first = upload(client, a, content)
    again = upload(client, a, content)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["duplicate_upload"] is True
    assert again.json()["batch"]["id"] == first.json()["batch"]["id"]


def test_idempotent_recommit(client, world):
    a = world["a"]
    batch_id = upload(client, a, to_csv(rows_for(world, a, "UG-CSE", 3, start=201))).json()[
        "batch"
    ]["id"]
    once = commit(client, a, batch_id).json()
    twice = commit(client, a, batch_id).json()
    assert once == twice
    assert once["rows_committed"] == 3


def test_error_rows_excluded(client, world):
    a = world["a"]
    rows = rows_for(world, a, "UG-CSE", 3, start=301)
    rows[1]["apaar_id"] = "123"
    batch = upload(client, a, to_csv(rows)).json()["batch"]
    assert batch["counts"]["errors"] == 1
    issues = client.get(f"/batches/{batch['id']}/issues", headers=as_institution(a)).json()
    assert {(i["row_number"], i["rule_code"]) for i in issues} == {(2, "APAAR_FORMAT")}
    result = commit(client, a, batch["id"]).json()
    assert (result["rows_committed"], result["rows_rejected"]) == (2, 1)


# ---------------------------------------------------------------------------- Seat Ledger
def test_overrun_71_into_60_creates_one_case(client, world):
    a = world["a"]
    batch = upload(client, a, to_csv(rows_for(world, a, "UG-CE", 71, start=1001))).json()["batch"]
    result = commit(client, a, batch["id"]).json()
    assert result["rows_committed"] == 71  # recorded and flagged, never dropped

    cases = [
        c
        for c in client.get("/review-cases?kind=intake_overrun", headers=AICTE).json()
        if c["institution_id"] == a["id"] and c["evidence"]["programme"] == "UG-CE"
    ]
    assert len(cases) == 1
    evidence = cases[0]["evidence"]
    assert (evidence["approved"], evidence["used"], evidence["overrun_by"]) == (60, 71, 11)
    assert evidence["pool"] == "regular" and evidence["rule_version"] == "TEST-v1"
    assert cases[0]["id"] in result["review_cases_created"]

    issues = client.get(f"/batches/{batch['id']}/issues", headers=as_institution(a)).json()
    flagged = sorted(i["row_number"] for i in issues if i["rule_code"] == "INTAKE_OVERRUN")
    assert flagged == list(range(61, 72))

    ledger = client.get(f"/institutions/{a['id']}/seat-ledger", headers=AICTE).json()
    ce = next(p for p in ledger["programmes"] if p["programme_code"] == "UG-CE")
    regular = next(p for p in ce["pools"] if p["pool"] == "regular")
    assert (regular["admitted"], regular["overrun"]) == (71, 11)


def test_cross_institution_duplicate(client, world):
    a, b = world["a"], world["b"]
    shared = rows_for(world, a, "UG-CSE", 1, start=501)
    commit(client, a, upload(client, a, to_csv(shared)).json()["batch"]["id"])

    at_b = rows_for(world, b, "UG-CSE", 1, start=501)
    batch = upload(client, b, to_csv(at_b)).json()["batch"]
    issues = client.get(f"/batches/{batch['id']}/issues", headers=as_institution(b)).json()
    dup = [i for i in issues if i["rule_code"] == "DUP_CROSS_INSTITUTION"]
    assert len(dup) == 1 and dup[0]["details"]["other_institution_code"] == a["code"]
    assert dup[0]["details"]["apaar_id_masked"].startswith("XXXX-XXXX-")

    result = commit(client, b, batch["id"]).json()
    signals = [
        c
        for c in client.get("/review-cases?kind=signal", headers=AICTE).json()
        if c["id"] in result["review_cases_created"]
    ]
    assert len(signals) == 1 and signals[0]["institution_id"] == b["id"]


# ---------------------------------------------------------------------------- scoping
def test_institution_scoping(client, world):
    a, b = world["a"], world["b"]
    batch_b = upload(client, b, to_csv(rows_for(world, b, "UG-CSE", 1, start=601))).json()
    batch_id = batch_b["batch"]["id"]

    assert client.get(f"/batches/{batch_id}", headers=as_institution(a)).status_code == 403
    assert commit(client, a, batch_id).status_code == 403
    assert (
        client.get(
            "/admissions", params={"institution_id": b["id"]}, headers=as_institution(a)
        ).status_code
        == 403
    )
    assert (
        client.get(f"/institutions/{b['id']}/seat-ledger", headers=as_institution(a)).status_code
        == 403
    )
    own = client.get("/admissions", params={"limit": 200}, headers=as_institution(a)).json()
    assert own and all(x["institution_id"] == a["id"] for x in own)
    cases = client.get("/review-cases", headers=as_institution(a)).json()
    assert all(c["institution_id"] == a["id"] for c in cases)
    listed = client.get("/institutions", headers=as_institution(a)).json()
    assert [i["id"] for i in listed] == [a["id"]]


def test_resolve_review_case_requires_note(client, world):
    a = world["a"]
    cases = [
        c
        for c in client.get("/review-cases?kind=intake_overrun", headers=AICTE).json()
        if c["institution_id"] == a["id"]
    ]
    case_id = cases[0]["id"]
    path = f"/review-cases/{case_id}/resolve"
    assert (
        client.post(path, json={"status": "confirmed", "note": ""}, headers=AICTE).status_code
        == 422
    )
    ok = client.post(path, json={"status": "confirmed", "note": "Checked."}, headers=AICTE)
    assert ok.status_code == 200 and ok.json()["status"] == "confirmed"
    denied = client.post(path, json={"status": "dismissed", "note": "x"}, headers=as_institution(a))
    assert denied.status_code == 403


# ---------------------------------------------------------------------------- audit chain
def test_audit_verify_ok(client, world):
    body = client.get("/audit/verify", headers=AICTE).json()
    assert body["ok"] is True and body["first_broken_index"] is None and body["checked"] > 0


def tamper(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.tamper_demo", *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_tamper_break_and_restore(client, world):
    with transaction() as conn:
        last = conn.execute("select max(id) as id from public.audit_events").fetchone()["id"]
        index = conn.execute(
            "select count(*) as n from public.audit_events where id < %s", (last,)
        ).fetchone()["n"]
    refused = subprocess.run(
        [sys.executable, "-m", "scripts.tamper_demo", "--break"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert refused.returncode != 0

    out = tamper("--break", "--yes", "--event-id", str(last))
    try:
        assert f"chain index {index}" in out
        broken = client.get("/audit/verify", headers=AICTE).json()
        assert broken["ok"] is False and broken["first_broken_index"] == index
    finally:
        tamper("--restore", "--yes")
    assert client.get("/audit/verify", headers=AICTE).json()["ok"] is True
