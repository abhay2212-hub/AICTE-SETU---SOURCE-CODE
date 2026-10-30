# Owner: Dev B
"""Edit requests are checked with the upload rules when filed, not only when approved."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.services import admissions as service
from app.services.validation import ADMISSION_MODES
from tests.conftest import as_role
from tests.test_edit_request_decisions import ADMISSION_ID, DEMO_OPERATOR

CUTOFF = date(2026, 9, 30)
INSTITUTION = "10000000-0000-4000-8000-000000000003"


@pytest.mark.parametrize(
    ("field", "new_value", "stored"),
    [
        ("admission_mode", "cap", "cap"),
        ("admission_mode", " Management ", "management"),
        ("admission_mode", "LATERAL", "lateral"),
        ("admission_date", "2026-08-08", "2026-08-08"),
        ("admission_date", "08/08/2026", "2026-08-08"),
        ("admission_date", "2026-09-30", "2026-09-30"),
        ("dob", "2008-03-14", "2008-03-14"),
        ("dob", "14.03.2008", "2008-03-14"),
        ("qualifying_exam_pct", "72.5", "72.5"),
        ("qualifying_exam_pct", "0", "0.0"),
        ("qualifying_exam_pct", "100", "100.0"),
        ("student_name", "  priya   kumari ", "Priya Kumari"),
        ("withdrawal", "withdrawn", "withdrawn"),
        ("withdrawal", "Withdrawn", "withdrawn"),
    ],
)
def test_valid_values_are_accepted_and_normalised(field, new_value, stored):
    assert service.check_edit_value(field, new_value, CUTOFF) == stored


@pytest.mark.parametrize(
    ("field", "new_value", "says"),
    [
        ("admission_mode", "online", "admission_mode must be one of cap, management, lateral"),
        ("admission_mode", "", "admission_mode is blank"),
        ("admission_date", "2026-13-01", "admission_date is not a valid date"),
        ("admission_date", "yesterday", "admission_date is not a valid date"),
        ("admission_date", "2026-10-01", "admission_date must be on or before"),
        ("admission_date", "", "admission_date is blank"),
        ("dob", "31/02/2008", "dob is not a valid date"),
        ("dob", " ", "dob is blank"),
        ("qualifying_exam_pct", "abc", "qualifying_exam_pct must be a number from 0 to 100"),
        ("qualifying_exam_pct", "100.5", "qualifying_exam_pct must be a number from 0 to 100"),
        ("qualifying_exam_pct", "-1", "qualifying_exam_pct must be a number from 0 to 100"),
        ("student_name", "", "student_name is blank"),
        ("student_name", "   ", "student_name is blank"),
        ("withdrawal", "yes", "must be 'withdrawn'"),
    ],
)
def test_invalid_values_are_422_invalid_edit_value(field, new_value, says):
    with pytest.raises(HTTPException) as refused:
        service.check_edit_value(field, new_value, CUTOFF)
    assert refused.value.status_code == 422
    detail = refused.value.detail
    assert detail["code"] == "INVALID_EDIT_VALUE"
    assert detail["field"] == field
    assert says in detail["message"]


def test_enum_errors_list_the_allowed_values():
    with pytest.raises(HTTPException) as refused:
        service.check_edit_value("admission_mode", "online", CUTOFF)
    assert refused.value.detail["allowed_values"] == list(ADMISSION_MODES)
    assert refused.value.detail["message"] == (
        "admission_mode must be one of cap, management, lateral, spot."
    )


def test_cutoff_error_names_the_cutoff():
    with pytest.raises(HTTPException) as refused:
        service.check_edit_value("admission_date", "2026-10-01", CUTOFF)
    assert "2026-09-30" in refused.value.detail["message"]


def test_unknown_field_is_still_refused():
    with pytest.raises(HTTPException) as refused:
        service.check_edit_value("apaar_id", "123456789012", CUTOFF)
    assert refused.value.status_code == 422
    assert "field must be one of" in refused.value.detail


def test_every_editable_field_is_described():
    assert set(service.FIELD_TYPES) == {*service.EDITABLE, service.WITHDRAWAL}


def test_invalid_value_is_refused_before_anything_is_written(monkeypatch):
    class NoWrites:
        def execute(self, *args, **kwargs):
            raise AssertionError("nothing should be read or written")

    monkeypatch.setattr(
        service.audit_store, "append_event", lambda *a: pytest.fail("audited a refused request")
    )
    body = {"field": "admission_mode", "new_value": "online", "reason": "Typo."}
    with pytest.raises(HTTPException) as refused:
        service.create_edit_request(NoWrites(), ADMISSION_ID, body, DEMO_OPERATOR)
    assert refused.value.detail["code"] == "INVALID_EDIT_VALUE"


def test_valid_value_is_stored_normalised(monkeypatch):
    from tests.test_edit_request_decisions import FakeConn

    monkeypatch.setattr(service.audit_store, "append_event", lambda *a: None)
    monkeypatch.setattr(
        service,
        "_load_admission",
        lambda conn, admission_id, user, lock=False: {"active": True, "admission_mode": "cap"},
    )
    conn = FakeConn()
    body = {"field": "admission_mode", "new_value": "SPOT", "reason": "Spot round."}
    request = service.create_edit_request(conn, ADMISSION_ID, body, DEMO_OPERATOR)
    assert request["new_value"] == conn.row["new_value"] == "spot"


# ---------------------------------------------------------------------------- fixture mode
def test_fixture_create_refuses_an_invalid_value(client):
    response = client.post(
        f"/admissions/{ADMISSION_ID}/edit-requests",
        json={"field": "admission_mode", "new_value": "online", "reason": "Typo."},
        headers=as_role("institution_operator", INSTITUTION),
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_EDIT_VALUE"
    assert detail["field"] == "admission_mode"
    assert detail["allowed_values"] == list(ADMISSION_MODES)


def test_fixture_create_refuses_a_date_after_the_cutoff(client):
    response = client.post(
        f"/admissions/{ADMISSION_ID}/edit-requests",
        json={"field": "admission_date", "new_value": "2026-10-15", "reason": "Late."},
        headers=as_role("institution_operator", INSTITUTION),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_EDIT_VALUE"


def test_fields_endpoint_lists_types_and_allowed_values(client):
    response = client.get("/edit-requests/fields", headers=as_role("institution_operator"))
    assert response.status_code == 200
    fields = {f["field"]: f for f in response.json()}
    assert set(fields) == set(service.FIELD_TYPES)
    assert fields["admission_mode"] == {
        "field": "admission_mode",
        "type": "enum",
        "allowed_values": list(ADMISSION_MODES),
    }
    assert fields["withdrawal"]["allowed_values"] == ["withdrawn"]
    assert fields["admission_date"] == {
        "field": "admission_date",
        "type": "date",
        "allowed_values": None,
    }
    assert fields["qualifying_exam_pct"]["type"] == "number"
    assert fields["student_name"]["type"] == "text"


def test_fields_endpoint_needs_a_staff_role(client):
    response = client.get("/edit-requests/fields", headers=as_role("student"))
    assert response.status_code == 403
