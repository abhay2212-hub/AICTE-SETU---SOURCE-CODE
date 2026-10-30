# Owner: Dev B
"""Edit requests record who requested and who decided them, as the audit event does."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.models.auth import User
from app.services import admissions as service
from tests.conftest import as_role

REQUEST_ID = "70000000-0000-4000-8000-0000000000aa"
FIXTURE_REQUEST_ID = "70000000-0000-4000-8000-000000000001"
ADMISSION_ID = "50000000-0000-4000-8000-000000000004"
DEMO_AICTE = User(id="demo-aicte_admin", role="aicte_admin", demo=True)
REAL_AICTE = User(id="8f2b6c1e-1111-4222-8333-444455556666", role="aicte_admin")
DEMO_OPERATOR = User(
    id="demo-institution_operator",
    role="institution_operator",
    institution_id="10000000-0000-4000-8000-000000000003",
    demo=True,
)
REAL_OPERATOR = User(
    id="3c9d2a7f-aaaa-4bbb-8ccc-ddddeeeeffff",
    role="institution_operator",
    institution_id="10000000-0000-4000-8000-000000000003",
)


class FakeConn:
    """Just enough of public.edit_requests for decide_edit_request."""

    def __init__(self) -> None:
        self.row = {
            "id": REQUEST_ID,
            "admission_id": ADMISSION_ID,
            "field": "admission_date",
            "old_value": "2026-08-28",
            "new_value": "2026-08-08",
            "reason": "Keyed from the fee receipt.",
            "status": "pending",
            "requested_by": "demo-institution_operator",
            "decided_by": None,
            "decision_note": None,
            "created_at": datetime(2026, 9, 3, tzinfo=UTC),
            "decided_at": None,
        }

    def execute(self, query: str, params: tuple = ()):
        sql = " ".join(query.split())
        result = None
        if sql.startswith("select * from public.edit_requests"):
            result = dict(self.row) if params[0] == self.row["id"] else None
        elif sql.startswith("update public.edit_requests"):
            decision, decided_by, note, _ = params
            self.row.update(
                status=decision,
                decided_by=decided_by,
                decision_note=note,
                decided_at=datetime.now(UTC),
            )
            result = dict(self.row)
        elif sql.startswith("insert into public.edit_requests"):
            admission_id, field, old_value, new_value, reason, requested_by = params
            self.row.update(
                admission_id=admission_id,
                field=field,
                old_value=old_value,
                new_value=new_value,
                reason=reason,
                requested_by=requested_by,
            )
            result = dict(self.row)
        # The admissions update applied on approval needs no result.
        return _Cursor(result)


class _Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


@pytest.fixture
def audit(monkeypatch):
    events: list[dict] = []

    def append_event(conn, actor, action, entity_type, entity_id, payload):
        events.append({"actor": actor, "action": action, "entity_id": str(entity_id)})

    monkeypatch.setattr(service.audit_store, "append_event", append_event)
    return events


@pytest.mark.parametrize("decision", ["approved", "rejected"])
@pytest.mark.parametrize("user", [DEMO_AICTE, REAL_AICTE], ids=["demo", "real"])
def test_decision_sets_decided_by_to_the_audit_actor(audit, decision, user):
    conn = FakeConn()
    request, _ = service.decide_edit_request(conn, REQUEST_ID, decision, "Checked.", user)
    assert request["status"] == decision
    assert request["decided_by"] == user.id
    assert conn.row["decided_by"] == user.id
    assert audit == [
        {"actor": user.id, "action": f"edit_request.{decision}", "entity_id": REQUEST_ID}
    ]
    assert request["decided_by"] == audit[0]["actor"]


def test_pending_request_keeps_decided_by_null():
    assert service._edit_request(FakeConn().row)["decided_by"] is None


@pytest.mark.parametrize("user", [DEMO_OPERATOR, REAL_OPERATOR], ids=["demo", "real"])
def test_create_stores_the_requesting_actor(audit, monkeypatch, user):
    monkeypatch.setattr(
        service,
        "_load_admission",
        lambda conn, admission_id, user, lock=False: {
            "active": True,
            "admission_date": "2026-08-28",
        },
    )
    conn = FakeConn()
    body = {"field": "admission_date", "new_value": "2026-08-08", "reason": "Fee receipt."}
    request = service.create_edit_request(conn, ADMISSION_ID, body, user)
    assert conn.row["requested_by"] == user.id
    assert request["requested_by"] == user.id
    assert request["decided_by"] is None
    assert audit == [{"actor": user.id, "action": "edit_request.created", "entity_id": REQUEST_ID}]


def test_legacy_row_without_requester_still_has_a_label():
    row = {**FakeConn().row, "requested_by": None}
    assert service._edit_request(row)["requested_by"] == "demo-user"


@pytest.mark.parametrize("first", ["approved", "rejected"])
def test_second_decision_is_refused_and_keeps_the_first_decider(audit, first):
    conn = FakeConn()
    service.decide_edit_request(conn, REQUEST_ID, first, None, DEMO_AICTE)
    with pytest.raises(HTTPException) as refused:
        service.decide_edit_request(conn, REQUEST_ID, "approved", None, REAL_AICTE)
    assert refused.value.status_code == 409
    assert conn.row["status"] == first
    assert conn.row["decided_by"] == DEMO_AICTE.id
    assert len(audit) == 1


# ---------------------------------------------------------------------------- fixture mode
def test_fixture_decision_returns_the_demo_actor(client):
    response = client.post(
        f"/edit-requests/{FIXTURE_REQUEST_ID}/decision",
        json={"decision": "rejected", "note": "No document."},
        headers=as_role("aicte_admin"),
    )
    assert response.status_code == 200
    assert response.json()["decided_by"] == "demo-aicte_admin"


def test_fixture_pending_requests_have_no_decider(client):
    rows = client.get("/edit-requests", params={"status": "pending"}, headers=as_role("auditor"))
    assert rows.json() and all(row["decided_by"] is None for row in rows.json())


def test_fixture_create_returns_the_requesting_actor(client):
    response = client.post(
        f"/admissions/{ADMISSION_ID}/edit-requests",
        json={"field": "admission_date", "new_value": "2026-08-08", "reason": "Fee receipt."},
        headers=as_role("institution_operator", "10000000-0000-4000-8000-000000000003"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["requested_by"] == "demo-institution_operator"
    assert response.json()["decided_by"] is None
