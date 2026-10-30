# Owner: Dev B
"""Fixtures for DB integration tests (RUN_DB_TESTS=1, DATABASE_URL in backend/.env).

Every run creates two institutions with codes prefixed TEST-, works only on them, and
deletes everything it created afterwards: audit events it appended and submission windows
for the far-future TEST_YEARS included.
"""

from __future__ import annotations

import os
import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import DOMAINS, get_settings
from app.core.db import close_pool, transaction
from app.main import app

RUN = os.environ.get("RUN_DB_TESTS") == "1"


def pytest_collection_modifyitems(config, items):
    if RUN:
        return
    skip = pytest.mark.skip(reason="DB integration tests run only with RUN_DB_TESTS=1")
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(skip)


POOL_SPLIT = {"regular": 60, "tfw": 3, "fn_oci_pio": 3, "nri": 3}
# Academic years only integration tests use, so their windows never touch real years.
TEST_YEARS = ("2097-98", "2098-99")


@pytest.fixture(scope="session")
def db_settings():
    settings = get_settings()
    if not settings.database_url:
        pytest.skip("DATABASE_URL is not configured in backend/.env")
    saved = settings.model_dump()
    settings.real_domains = ",".join(DOMAINS)
    if not settings.pseudonym_secret:
        settings.pseudonym_secret = "integration-test-secret"
    yield settings
    for key, value in saved.items():
        setattr(settings, key, value)
    close_pool()


def _make_institution(conn, run: str, suffix: str) -> dict:
    code = f"TEST-{run}-{suffix}"
    inst = conn.execute(
        "insert into public.institutions (aicte_code, name, state)"
        " values (%s, %s, 'Test State') returning id",
        (code, f"Test Institute {suffix} {run}"),
    ).fetchone()
    programmes = {}
    # UG-IT is used only by test_demo_flows_db, so test_pipeline_db sees untouched pools.
    for programme in ("UG-CSE", "UG-CE", "UG-IT"):
        row = conn.execute(
            "insert into public.programmes (institution_id, code, name)"
            " values (%s, %s, %s) returning id",
            (inst["id"], programme, f"Test {programme}"),
        ).fetchone()
        programmes[programme] = str(row["id"])
        for year in ("2026-27", *TEST_YEARS):
            for pool, seats in POOL_SPLIT.items():
                conn.execute(
                    "insert into public.seat_pools"
                    " (programme_id, academic_year, pool, approved_seats, rule_version)"
                    " values (%s, %s, %s, %s, 'TEST-v1')",
                    (row["id"], year, pool, seats),
                )
    return {"id": str(inst["id"]), "code": code, "programmes": programmes}


@pytest.fixture(scope="session")
def world(db_settings):
    run = secrets.token_hex(3).upper()
    with transaction() as conn:
        start = conn.execute("select coalesce(max(id), 0) as m from public.audit_events").fetchone()
        a = _make_institution(conn, run, "A")
        b = _make_institution(conn, run, "B")
        # Synthetic APAAR IDs unique to this run: 9999 + 4 random digits + 4-digit serial,
        # with a prefix no existing student uses, so cleanup only touches this run's rows.
        while True:
            prefix = f"9999{secrets.randbelow(10**4):04d}"
            taken = conn.execute(
                "select 1 from public.students where apaar_id like %s limit 1", (f"{prefix}%",)
            ).fetchone()
            if not taken:
                break
    yield {"run": run, "a": a, "b": b, "apaar_prefix": prefix}
    _cleanup([a["id"], b["id"]], prefix, start["m"])


def _cleanup(institution_ids: list[str], apaar_prefix: str, audit_start: int) -> None:
    with transaction() as conn:
        batches = [
            r["id"]
            for r in conn.execute(
                "select id from public.batches where institution_id = any(%s::uuid[])",
                (institution_ids,),
            ).fetchall()
        ]
        cases = [
            r["id"]
            for r in conn.execute(
                "select id from public.review_cases where institution_id = any(%s::uuid[])",
                (institution_ids,),
            ).fetchall()
        ]
        conn.execute(
            "delete from public.admissions where programme_id in (select id from"
            " public.programmes where institution_id = any(%s::uuid[]))",
            (institution_ids,),
        )
        conn.execute("delete from public.review_cases where id = any(%s)", (cases,))
        conn.execute("delete from public.batches where id = any(%s)", (batches,))
        conn.execute(
            "delete from public.api_keys where institution_id = any(%s::uuid[])",
            (institution_ids,),
        )
        conn.execute(
            "delete from public.students where apaar_id like %s",
            (f"{apaar_prefix}%",),
        )
        conn.execute(
            "delete from public.institutions where id = any(%s::uuid[])", (institution_ids,)
        )
        conn.execute(
            "delete from public.submission_windows where academic_year = any(%s)",
            (list(TEST_YEARS),),
        )
        # This run's audit events sit at the tail of the chain (batches, cases, admissions,
        # edit requests, windows, keys); removing the whole tail keeps the chain intact.
        # Do not run the integration tests while another writer is using the database.
        conn.execute("delete from public.audit_events where id > %s", (audit_start,))


@pytest.fixture
def client(db_settings) -> TestClient:
    return TestClient(app)


def as_institution(inst: dict, role: str = "institution_admin") -> dict[str, str]:
    return {"X-Demo-Role": role, "X-Demo-Institution": inst["id"]}


AICTE = {"X-Demo-Role": "aicte_admin"}


def new_id() -> str:
    return str(uuid.uuid4())
