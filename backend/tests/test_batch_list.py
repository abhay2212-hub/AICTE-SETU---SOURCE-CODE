# Owner: Dev B
"""GET /batches: scoping, filters, paging and order, on fixtures and on the SQL path."""

from __future__ import annotations

import pytest

from app.models.auth import User
from app.routers import batches as router
from app.services import batches as service
from tests.conftest import as_role

SHADOW = "10000000-0000-4000-8000-000000000003"
OTHER = "10000000-0000-4000-8000-000000000001"
FIXTURE_BATCH = "30000000-0000-4000-8000-000000000001"


def batch(n: int, institution: str, created: str, **extra) -> dict:
    return {
        "id": f"30000000-0000-4000-8000-{n:012d}",
        "institution_id": institution,
        "uploaded_by": "demo-institution_admin",
        "file_name": f"upload-{n}.csv",
        "file_hash": f"{n:064x}",
        "status": "committed",
        "counts": {"rows_total": 10},
        "created_at": created,
        "parent_batch_id": None,
        **extra,
    }


ORIGINAL = batch(1, SHADOW, "2026-09-02T09:40:00Z")
CORRECTION = batch(2, SHADOW, "2026-09-05T10:00:00Z", parent_batch_id=ORIGINAL["id"])
NEXT_YEAR = batch(3, SHADOW, "2026-09-10T08:00:00Z", status="validated")
OTHER_INST = batch(4, OTHER, "2026-09-12T08:00:00Z")
YEARS = {
    ORIGINAL["id"]: {"2026-27"},
    CORRECTION["id"]: {"2026-27"},
    NEXT_YEAR["id"]: {"2027-28"},
    OTHER_INST["id"]: {"2026-27"},
}


@pytest.fixture
def fixtures(monkeypatch):
    monkeypatch.setattr(
        router, "_fixture_batches", lambda: [ORIGINAL, CORRECTION, NEXT_YEAR, OTHER_INST]
    )
    monkeypatch.setattr(router, "_fixture_years", lambda: YEARS)


def ids(response) -> list[str]:
    assert response.status_code == 200, response.text
    return [b["id"] for b in response.json()["items"]]


# ---------------------------------------------------------------------------- fixture fallback
def test_fixture_fallback_lists_the_batch_fixture(client):
    response = client.get("/batches", headers=as_role("institution_admin", SHADOW))
    assert response.headers["X-Mock"] == "true"
    body = response.json()
    assert body == {"items": body["items"], "total": 1, "limit": 50, "offset": 0}
    assert body["items"][0]["id"] == FIXTURE_BATCH
    assert body["items"][0]["parent_batch_id"] is None
    assert client.get(f"/batches/{FIXTURE_BATCH}").json() == body["items"][0]


def test_fixture_year_comes_from_its_admissions(client):
    headers = as_role("aicte_admin")
    assert ids(client.get("/batches?academic_year=2026-27", headers=headers)) == [FIXTURE_BATCH]
    assert ids(client.get("/batches?academic_year=2030-31", headers=headers)) == []


# ---------------------------------------------------------------------------- access
@pytest.mark.parametrize("role", ["student", "verifier"])
def test_other_roles_get_403(client, role):
    assert client.get("/batches", headers=as_role(role)).status_code == 403


def test_institution_user_without_institution_gets_403(client):
    assert client.get("/batches", headers=as_role("institution_operator")).status_code == 403


@pytest.mark.parametrize("role", ["institution_admin", "institution_operator"])
def test_institution_user_sees_only_own_batches(client, fixtures, role):
    headers = as_role(role, SHADOW)
    own = [NEXT_YEAR["id"], CORRECTION["id"], ORIGINAL["id"]]
    assert ids(client.get("/batches", headers=headers)) == own
    # institution_id is ignored for institution users, never a way into another institution.
    assert ids(client.get(f"/batches?institution_id={OTHER}", headers=headers)) == own


@pytest.mark.parametrize("role", ["aicte_admin", "auditor"])
def test_aicte_and_auditor_see_all_and_filter_by_institution(client, fixtures, role):
    headers = as_role(role)
    assert len(ids(client.get("/batches", headers=headers))) == 4
    assert ids(client.get(f"/batches?institution_id={OTHER}", headers=headers)) == [
        OTHER_INST["id"]
    ]


# ---------------------------------------------------------------------------- filters
def test_filters(client, fixtures):
    headers = as_role("aicte_admin")
    assert ids(client.get("/batches?status=validated", headers=headers)) == [NEXT_YEAR["id"]]
    assert ids(client.get("/batches?academic_year=2027-28", headers=headers)) == [NEXT_YEAR["id"]]
    assert ids(client.get(f"/batches?parent_batch_id={ORIGINAL['id']}", headers=headers)) == [
        CORRECTION["id"]
    ]
    both = f"/batches?institution_id={SHADOW}&academic_year=2026-27&status=committed"
    assert ids(client.get(both, headers=headers)) == [CORRECTION["id"], ORIGINAL["id"]]
    assert client.get("/batches?status=nope", headers=headers).status_code == 422


# ---------------------------------------------------------------------------- paging and order
def test_newest_first(client, fixtures):
    items = client.get("/batches", headers=as_role("aicte_admin")).json()["items"]
    created = [b["created_at"] for b in items]
    assert created == sorted(created, reverse=True)
    assert items[0]["id"] == OTHER_INST["id"]


def test_pagination(client, fixtures):
    headers = as_role("aicte_admin")
    body = client.get("/batches?limit=2&offset=1", headers=headers).json()
    assert [b["id"] for b in body["items"]] == [NEXT_YEAR["id"], CORRECTION["id"]]
    assert (body["total"], body["limit"], body["offset"]) == (4, 2, 1)
    past_end = client.get("/batches?offset=10", headers=headers).json()
    assert (past_end["items"], past_end["total"]) == ([], 4)


@pytest.mark.parametrize(
    ("query", "code"),
    [("limit=200", 200), ("limit=201", 422), ("limit=0", 422), ("offset=-1", 422)],
)
def test_pagination_bounds(client, query, code):
    assert client.get(f"/batches?{query}", headers=as_role("aicte_admin")).status_code == code


# ---------------------------------------------------------------------------- SQL path
class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class FakeConn:
    """Records each query; returns a count, then the stored rows."""

    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if sql.startswith("select count(*)"):
            return FakeCursor([{"n": len(self.rows)}])
        return FakeCursor(self.rows)


def user(role: str, institution: str | None = None) -> User:
    return User(id=f"demo-{role}", role=role, institution_id=institution, display_name="x")


def db_row(b: dict) -> dict:
    return {**b, "uploaded_by": None}


def test_sql_scopes_institution_user_to_own_institution():
    conn = FakeConn([db_row(ORIGINAL)])
    filters = {"institution_id": OTHER}
    page = service.list_batches(conn, user("institution_admin", SHADOW), filters, 50, 0)
    for sql, params in conn.calls:
        assert "b.institution_id = %s" in sql
        assert SHADOW in params and OTHER not in params
    assert page["total"] == 1 and page["items"][0]["id"] == ORIGINAL["id"]


def test_sql_filters_order_and_paging():
    conn = FakeConn([])
    filters = {
        "institution_id": SHADOW,
        "status": "committed",
        "parent_batch_id": ORIGINAL["id"],
        "academic_year": "2026-27",
    }
    page = service.list_batches(conn, user("auditor"), filters, 500, 20)
    (count_sql, count_params), (sql, params) = conn.calls
    for clause in ("b.institution_id = %s", "b.parent_batch_id = %s", "b.status::text = %s"):
        assert clause in sql and clause in count_sql
    assert "->>'academic_year' = %s" in sql
    assert sql.endswith("order by b.created_at desc, b.id desc limit %s offset %s")
    assert params[-2:] == (service.MAX_LIMIT, 20) and count_params == params[:-2]
    assert (page["limit"], page["offset"]) == (service.MAX_LIMIT, 20)


def test_sql_unscoped_for_aicte_admin_and_bad_ids_match_nothing():
    conn = FakeConn([])
    service.list_batches(conn, user("aicte_admin"), {}, 50, 0)
    assert "where" not in conn.calls[0][0]
    conn = FakeConn([])
    page = service.list_batches(conn, user("aicte_admin"), {"parent_batch_id": "x"}, 50, 0)
    assert page["items"] == [] and page["total"] == 0 and conn.calls == []
