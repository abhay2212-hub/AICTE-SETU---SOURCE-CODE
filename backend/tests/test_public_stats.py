# Owner: Dev B
"""GET /public/stats: aggregates only, no sign-in, fixture or Postgres per domain."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager

import pytest

from app.core.audit import verify_chain
from app.mocks import mock
from app.routers import public as router

FIELDS = {
    "institutions",
    "active_admissions",
    "open_review_cases",
    "audit_chain_ok",
    "audit_events",
    "academic_year",
}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()):
        self.calls.append((sql, params))
        if "from public.institutions" in sql:
            return FakeCursor({"n": 41})
        if "from public.admissions" in sql:
            return FakeCursor({"n": 5464})
        if "from public.review_cases" in sql:
            return FakeCursor({"n": 7})
        raise AssertionError(f"unexpected query: {sql}")


@pytest.fixture
def real_db(settings_override, monkeypatch):
    conn = FakeConn()

    @contextmanager
    def fake_transaction():
        yield conn

    monkeypatch.setattr(router, "transaction", fake_transaction)
    monkeypatch.setattr(
        router.audit_store,
        "verify",
        lambda _conn: {"ok": True, "first_broken_index": None, "checked": 120},
    )
    return conn


def assert_no_identifiers(body: dict) -> None:
    assert set(body) == FIELDS
    assert not UUID.search(json.dumps(body))
    for key, value in body.items():
        if key != "academic_year":
            assert isinstance(value, bool | int), key


def test_fixture_counts(client):
    r = client.get("/public/stats")
    assert r.status_code == 200, r.text
    assert r.headers["X-Mock"] == "true"
    body = r.json()
    events = mock("audit_events")
    assert body == {
        "institutions": len(mock("institutions")),
        "active_admissions": mock("enrolment_report")["state"]["total"],
        "open_review_cases": sum(1 for c in mock("review_cases") if c["status"] == "open"),
        "audit_chain_ok": verify_chain(events) is None,
        "audit_events": len(events),
        "academic_year": "2026-27",
    }
    assert_no_identifiers(body)


@pytest.mark.parametrize(
    "role", ["student", "verifier", "institution_operator", "aicte_admin", "auditor"]
)
def test_every_demo_role_gets_the_same_stats(client, role):
    anonymous = client.get("/public/stats").json()
    r = client.get("/public/stats", headers={"X-Demo-Role": role})
    assert r.status_code == 200
    assert r.json() == anonymous


def test_no_auth_needed_outside_mock_mode(client, settings_override):
    settings_override(mock_mode=False)
    assert client.get("/institutions").status_code == 401
    r = client.get("/public/stats")
    assert r.status_code == 200
    assert_no_identifiers(r.json())


def test_real_counts(client, real_db, settings_override):
    settings_override(real_domains="institutions,admissions,review_cases,audit")
    r = client.get("/public/stats")
    assert r.status_code == 200, r.text
    assert r.headers["X-Mock"] == "false"
    body = r.json()
    assert body == {
        "institutions": 41,
        "active_admissions": 5464,
        "open_review_cases": 7,
        "audit_chain_ok": True,
        "audit_events": 120,
        "academic_year": "2026-27",
    }
    assert_no_identifiers(body)
    admissions_sql, params = next(c for c in real_db.calls if "public.admissions" in c[0])
    assert "active" in admissions_sql
    assert params == ("2026-27",)
    assert any("status = 'open'" in sql for sql, _ in real_db.calls)


def test_mixed_sources_report_mock(client, real_db, settings_override):
    settings_override(real_domains="institutions")
    r = client.get("/public/stats")
    assert r.status_code == 200
    assert r.headers["X-Mock"] == "true"
    body = r.json()
    assert body["institutions"] == 41
    assert body["active_admissions"] == mock("enrolment_report")["state"]["total"]
    assert len(real_db.calls) == 1
