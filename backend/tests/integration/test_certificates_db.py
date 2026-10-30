# Owner: Dev B
"""F12 enrolment certificate against Postgres, on a TEST- institution only.

Run: RUN_DB_TESTS=1 uv run pytest tests/integration/test_certificates_db.py -q
The world fixture removes this run's students (credentials and access-log rows cascade),
institutions and audit-event tail; this module also removes its revocations.
"""

from __future__ import annotations

import pytest

from app.core.db import transaction
from app.services import credentials
from tests.integration.conftest import AICTE, as_institution
from tests.integration.test_pipeline_db import commit, rows_for, to_csv, upload

pytestmark = pytest.mark.db


@pytest.fixture
def certified(world, client, db_settings):
    saved = db_settings.credential_signing_key
    db_settings.credential_signing_key = saved or credentials.TEST_SEED_HEX
    a = world["a"]
    rows = rows_for(world, a, "UG-CSE", 1, start=8001)
    batch = upload(client, a, to_csv(rows)).json()["batch"]
    assert batch["status"] == "validated", batch
    assert commit(client, a, batch["id"]).json()["rows_committed"] == 1
    with transaction() as conn:
        student = conn.execute(
            "select id from public.students where apaar_id = %s", (rows[0]["apaar_id"],)
        ).fetchone()
    student_id = str(student["id"])
    yield {"student_id": student_id, "apaar_id": rows[0]["apaar_id"], "inst": a}
    with transaction() as conn:
        conn.execute(
            "delete from public.credential_revocations where student_id = %s", (student_id,)
        )
    db_settings.credential_signing_key = saved


def test_certificate_issue_verify_revoke(client, certified):
    student_id, apaar_id = certified["student_id"], certified["apaar_id"]
    r = client.get(f"/certificates/{student_id}", headers=AICTE)
    assert r.status_code == 200, r.text
    assert r.headers["X-Mock"] == "false"
    body = r.json()
    cert_id, qr_text = body["certificate_no"], body["qr_text"]
    assert apaar_id not in r.text
    assert body["apaar_id"] == f"XXXX-XXXX-{apaar_id[-4:]}"

    verified = client.post("/credentials/verify", json={"qr_text": qr_text}).json()
    assert verified["valid"] is True, verified
    assert verified["claims"]["institution"].startswith("Test Institute A")

    with transaction() as conn:
        event = conn.execute(
            "select actor, payload from public.audit_events"
            " where action = 'certificate.issued' and entity_id = %s",
            (cert_id,),
        ).fetchone()
        purposes = [
            r["purpose"]
            for r in conn.execute(
                "select purpose from public.access_log where student_id = %s", (student_id,)
            ).fetchall()
        ]
        stored = conn.execute(
            "select audience from public.credentials where id = %s", (cert_id,)
        ).fetchone()
    assert event is not None
    assert apaar_id not in str(event["payload"])
    assert "enrolment certificate issued" in purposes
    assert "credential verification" in purposes
    assert stored["audience"] == "enrolment-certificate"

    # The institution's own staff may issue it; another institution may not.
    own = client.get(
        f"/certificates/{student_id}",
        params={"format": "pdf"},
        headers=as_institution(certified["inst"]),
    )
    assert own.status_code == 200 and own.content.startswith(b"%PDF")
    other = {
        "X-Demo-Role": "institution_admin",
        "X-Demo-Institution": "00000000-0000-4000-8000-000000000000",
    }
    assert client.get(f"/certificates/{student_id}", headers=other).status_code == 403

    # The student revokes the credential, so the certificate stops verifying.
    student = {"X-Demo-Role": "student", "X-Demo-Student": student_id}
    revoked = client.post(
        f"/credentials/{cert_id}/revoke", json={"reason": "test"}, headers=student
    )
    assert revoked.status_code == 200, revoked.text
    again = client.post("/credentials/verify", json={"qr_text": qr_text}).json()
    assert again["valid"] is False and again["reason"] == "revoked"
