# Owner: Dev B
"""GET /reports/states (F27 map): roles, fixture/real switch, totals, ordering, aggregates only."""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from app.mocks import mock
from app.routers import reports as router
from app.services import state_report
from tests.conftest import as_role

AICTE = as_role("aicte_admin")
COUNTS = (
    "institutions",
    "active_admissions",
    "approved_seats",
    "overrun_programmes",
    "open_review_cases",
)
ROW_FIELDS = {
    "state",
    "institutions",
    "active_admissions",
    "approved_seats",
    "utilisation",
    "overrun_programmes",
    "open_review_cases",
    "avg_integrity_score",
    "institutions_list",
}
INSTITUTION_FIELDS = {
    "institution_id",
    "name",
    "aicte_code",
    "integrity_score",
    "open_review_cases",
    "overrun",
}
STUDENT_WORDS = ("apaar", "student", "dob", "phone", "email", "guardian", "provisional")

# Real mode: Gujarat has a zero-seat institution, Assam an institution with no programmes.
INSTITUTIONS = [
    {"id": "i-guj-1", "name": "Gir Tech", "aicte_code": "1-1", "state": "Gujarat"},
    {"id": "i-guj-2", "name": "Ahmedabad Poly", "aicte_code": "1-2", "state": "Gujarat"},
    {"id": "i-guj-3", "name": "Zero Seat College", "aicte_code": "1-3", "state": "Gujarat"},
    {"id": "i-asm-1", "name": "Brahmaputra Institute", "aicte_code": "1-4", "state": "Assam"},
]
PROGRAMMES = [
    {"institution_id": "i-guj-1", "approved": 60, "admitted": 71},
    {"institution_id": "i-guj-1", "approved": 60, "admitted": 30},
    {"institution_id": "i-guj-2", "approved": 120, "admitted": 100},
    {"institution_id": "i-guj-3", "approved": 0, "admitted": 4},
]
CASES = [{"institution_id": "i-guj-1", "n": 2}, {"institution_id": "i-asm-1", "n": 1}]
RANKINGS = [
    {"institution_id": "i-guj-1", "integrity_score": 41.0},
    {"institution_id": "i-guj-2", "integrity_score": 88.5},
]


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()):
        self.calls.append((sql, params))
        if "from public.institutions" in sql:
            return FakeCursor(INSTITUTIONS)
        if "from public.programmes p" in sql:
            return FakeCursor(PROGRAMMES)
        if "from public.review_cases" in sql:
            return FakeCursor(CASES)
        raise AssertionError(f"unexpected query: {sql}")


@pytest.fixture
def real_db(settings_override, monkeypatch):
    settings_override(real_domains="reports")
    conn = FakeConn()

    @contextmanager
    def fake_transaction():
        yield conn

    years: list[str | None] = []

    def rankings(_conn, academic_year=None):
        years.append(academic_year)
        return RANKINGS

    monkeypatch.setattr(router, "transaction", fake_transaction)
    monkeypatch.setattr(state_report.integrity_store, "latest_rankings", rankings)
    conn.ranking_years = years
    return conn


def assert_aggregates_only(body: dict) -> None:
    text = json.dumps(body).lower()
    for word in STUDENT_WORDS:
        assert word not in text, word
    for row in body["rows"]:
        assert set(row) == ROW_FIELDS
        for institution in row["institutions_list"]:
            assert set(institution) == INSTITUTION_FIELDS


def assert_totals(body: dict) -> None:
    for key in COUNTS:
        assert body["totals"][key] == sum(row[key] for row in body["rows"]), key
    assert body["totals"]["states"] == len(body["rows"])


# --------------------------------------------------------------------------- roles + fixture
@pytest.mark.parametrize("role", ["aicte_admin", "auditor"])
def test_aicte_roles_get_fixture_report(client, role):
    r = client.get("/reports/states", headers=as_role(role))
    assert r.status_code == 200, r.text
    assert r.headers["X-Mock"] == "true"
    body = r.json()
    assert body["academic_year"] == "2026-27"
    assert_totals(body)
    assert_aggregates_only(body)
    up = next(row for row in body["rows"] if row["state"] == "Uttar Pradesh")
    shadow = up["institutions_list"][0]
    assert shadow["name"] == "Shadow Institute of Technology" and shadow["overrun"] is True
    assert up["overrun_programmes"] == 1


@pytest.mark.parametrize(
    "headers",
    [
        as_role("institution_admin", "10000000-0000-4000-8000-000000000003"),
        as_role("institution_operator", "10000000-0000-4000-8000-000000000003"),
        as_role("student"),
        as_role("verifier"),
    ],
)
def test_other_roles_are_forbidden(client, headers):
    assert client.get("/reports/states", headers=headers).status_code == 403


def test_fixture_matches_the_other_fixtures():
    """mocks/state_report.json is generated from the institution, ledger and case fixtures."""
    built = state_report.from_fixtures(
        mock("institutions"), mock("seat_ledger"), mock("review_cases"), "2026-27"
    )
    assert mock("state_report")["2026-27"] == json.loads(json.dumps(built))
    assert built["totals"]["active_admissions"] == mock("enrolment_report")["state"]["total"]


def test_unknown_year_in_fixture_mode_is_404(client):
    assert client.get("/reports/states?academic_year=2030-31", headers=AICTE).status_code == 404


# ---------------------------------------------------------------------------------- real mode
def test_real_report(client, real_db):
    r = client.get("/reports/states", params={"academic_year": "2026-27"}, headers=AICTE)
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Mock") != "true"
    body = r.json()
    assert_totals(body)
    assert_aggregates_only(body)
    rows = {row["state"]: row for row in body["rows"]}
    assert list(rows) == ["Assam", "Gujarat"]

    gujarat = rows["Gujarat"]
    assert gujarat["institutions"] == 3
    assert gujarat["active_admissions"] == 205
    assert gujarat["approved_seats"] == 240
    assert gujarat["utilisation"] == round(205 / 240, 4)
    # Gir Tech's first programme (71 > 60) and the zero-seat college's programme (4 > 0).
    assert gujarat["overrun_programmes"] == 2
    assert gujarat["open_review_cases"] == 2
    assert gujarat["avg_integrity_score"] == round((41.0 + 88.5) / 2, 1)
    # Lowest score first, unscored last.
    assert [i["name"] for i in gujarat["institutions_list"]] == [
        "Gir Tech",
        "Ahmedabad Poly",
        "Zero Seat College",
    ]
    assert [i["overrun"] for i in gujarat["institutions_list"]] == [True, False, True]

    assam = rows["Assam"]
    assert assam["approved_seats"] == 0 and assam["utilisation"] is None
    assert assam["avg_integrity_score"] is None
    assert assam["open_review_cases"] == 1


def test_real_queries_are_parameterised_and_scoped(client, real_db):
    client.get("/reports/states", params={"academic_year": "2025-26"}, headers=AICTE)
    programme_sql, params = next(c for c in real_db.calls if "from public.programmes p" in c[0])
    assert "a.active" in programme_sql
    assert "distinct on (sp.programme_id, sp.pool)" in programme_sql
    assert "rule_version desc" in programme_sql
    assert params == ("2025-26", "2025-26")
    cases_sql, case_params = next(c for c in real_db.calls if "from public.review_cases" in c[0])
    assert "status = 'open'" in cases_sql and case_params == ("2025-26",)
    assert real_db.ranking_years == ["2025-26"]
    assert all("2025-26" not in sql for sql, _ in real_db.calls)


def test_real_forbidden_before_any_query(client, real_db):
    r = client.get("/reports/states", headers=as_role("student"))
    assert r.status_code == 403
    assert real_db.calls == []


def test_utilisation_null_for_zero_seats():
    report = state_report.build(
        [{"id": "x", "name": "X", "aicte_code": "1", "state": "Goa"}],
        [{"institution_id": "x", "approved": 0, "admitted": 0}],
        {},
        {},
        "2026-27",
    )
    (row,) = report["rows"]
    assert row["utilisation"] is None and row["overrun_programmes"] == 0
