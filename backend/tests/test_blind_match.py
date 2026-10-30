# Owner: Dev B
"""Cross-institution Blind Match (app.services.blind_match) with the fake encoder."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from app.models.auth import User
from app.services import blind_match as bm
from app.services.validation import dob_block_key
from tests import fake_engine
from tests.conftest import as_role

SECRET = "test-secret"
INST_A = "10000000-0000-4000-8000-0000000000aa"
INST_B = "10000000-0000-4000-8000-0000000000bb"
DOB = date(2008, 3, 14)


def candidate(
    student_id: str,
    name: str,
    institution: str,
    apaar: str | None = None,
    provisional: str | None = None,
    guardian: str | None = "Rakesh Sharma",
    dob: date = DOB,
) -> bm.Candidate:
    fields = bm.identity_fields(name, dob, guardian)
    return bm.Candidate(
        student_id=student_id,
        block=dob_block_key(dob, SECRET),
        bloom=fake_engine.encode_identity(fields, SECRET.encode(), bits=1024),
        apaar_id=apaar,
        provisional_id=provisional,
        has_guardian=bool(guardian),
        placements=(
            bm.Placement(institution, "UG-CSE", "2026-27", datetime(2026, 8, 1, tzinfo=UTC)),
        ),
    )


def sid(n: int) -> str:
    return f"40000000-0000-4000-8000-{n:012d}"


def test_different_valid_apaar_across_institutions_is_matched():
    a = candidate(sid(1), "Aarav Sharma", INST_A, apaar="999900000001")
    b = candidate(sid(2), "Aarav Sharmaa", INST_B, apaar="999900000002")
    matches = bm.find_matches([a, b], 0.85)
    assert len(matches) == 1
    assert matches[0].pair_key == f"{sid(1)}:{sid(2)}"
    assert matches[0].dice >= 0.85


def test_missing_apaar_across_institutions_is_matched():
    a = candidate(sid(1), "Aarav Sharma", INST_A, apaar="999900000001")
    b = candidate(sid(2), "Arav Sharma", INST_B, provisional="PROV-1-9999002-0001")
    assert len(bm.find_matches([a, b], 0.85)) == 1


def test_same_apaar_is_not_matched():
    a = candidate(sid(1), "Aarav Sharma", INST_A, apaar="999900000001")
    b = candidate(sid(2), "Aarav Sharma", INST_B, apaar="999900000001")
    assert bm.find_matches([a, b], 0.85) == []


def test_same_provisional_id_is_not_matched():
    a = candidate(sid(1), "Aarav Sharma", INST_A, provisional="PROV-X-0001")
    b = candidate(sid(2), "Aarav Sharma", INST_B, provisional="PROV-X-0001")
    assert bm.find_matches([a, b], 0.85) == []


def test_same_institution_is_not_matched():
    a = candidate(sid(1), "Aarav Sharma", INST_A, apaar="999900000001")
    b = candidate(sid(2), "Aarav Sharmaa", INST_A, apaar="999900000002")
    assert bm.find_matches([a, b], 0.85) == []


def test_different_dob_block_is_not_compared():
    a = candidate(sid(1), "Aarav Sharma", INST_A)
    b = candidate(sid(2), "Aarav Sharma", INST_B, dob=date(2008, 3, 15))
    assert bm.find_matches([a, b], 0.0) == []


def test_unrelated_people_with_same_dob_stay_below_threshold():
    a = candidate(sid(1), "Aarav Sharma", INST_A, guardian="Rakesh Sharma")
    b = candidate(sid(2), "Priya Nair", INST_B, guardian="Suresh Nair")
    assert bm.find_matches([a, b], 0.85) == []


def test_targets_limit_comparisons_and_each_pair_appears_once():
    a = candidate(sid(1), "Aarav Sharma", INST_A)
    b = candidate(sid(2), "Aarav Sharmaa", INST_B)
    c = candidate(sid(3), "Aarav Sharm", INST_B)
    # Both students are targets: the pair is still compared once.
    both = bm.find_matches([b, a], 0.85, targets={sid(1), sid(2)})
    assert [m.pair_key for m in both] == [bm.pair_key(sid(1), sid(2))]
    # Only c is a target: a-b is not compared, a-c is; b-c are at the same institution.
    only_c = bm.find_matches([a, b, c], 0.85, targets={sid(3)})
    assert [m.pair_key for m in only_c] == [bm.pair_key(sid(1), sid(3))]
    assert bm.pair_key(sid(2), sid(1)) == bm.pair_key(sid(1), sid(2))


def test_student_admitted_at_both_institutions_is_compared_cross_institution():
    a = candidate(sid(1), "Aarav Sharma", INST_A)
    both = bm.Candidate(
        **{
            **candidate(sid(2), "Aarav Sharmaa", INST_A).__dict__,
            "placements": (
                bm.Placement(INST_A, "UG-ME", "2026-27", datetime(2026, 8, 1, tzinfo=UTC)),
                bm.Placement(INST_B, "UG-CSE", "2026-27", datetime(2026, 8, 2, tzinfo=UTC)),
            ),
        }
    )
    [match] = bm.find_matches([a, both], 0.85)
    assert (match.place_a.institution_id, match.place_b.institution_id) == (INST_A, INST_B)


def test_evidence_has_no_raw_identity():
    a = candidate(sid(1), "Aarav Sharma", INST_A, apaar="999900000001")
    b = candidate(sid(2), "Aarav Sharmaa", INST_B, apaar="999900000002")
    evidence = bm.evidence(bm.find_matches([a, b], 0.85)[0])
    text = json.dumps(evidence).lower()
    for raw in ("aarav", "sharma", "rakesh", "2008", "999900000001", "999900000002"):
        assert raw not in text
    assert evidence["matched_on"] == ["name", "dob", "guardian"]
    assert set(evidence) == {
        "pair_key",
        "student_a_id",
        "student_b_id",
        "institution_a_id",
        "institution_b_id",
        "programme_a",
        "academic_year_a",
        "programme_b",
        "academic_year_b",
        "dice",
        "matched_on",
    }
    assert evidence["dice"] == round(evidence["dice"], 3)


def test_matched_on_leaves_out_guardian_when_one_side_has_none():
    a = candidate(sid(1), "Aarav Sharma", INST_A, guardian=None)
    b = candidate(sid(2), "Aarav Sharmaa", INST_B, guardian=None)
    assert bm.evidence(bm.find_matches([a, b], 0.85)[0])["matched_on"] == ["name", "dob"]


# ---------------------------------------------------------------------------- one case per pair
class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConn:
    """Stands in for the unique pair index: a second insert of a pair returns no row."""

    def __init__(self):
        self.pairs: dict[str, dict] = {}

    def execute(self, sql, params=()):
        assert "on conflict ((evidence->>'pair_key')) where kind = 'blind_match'" in sql
        institution, _title, evidence = params
        key = evidence.obj["pair_key"]
        if key in self.pairs:
            return FakeCursor(None)
        row = {
            "id": f"60000000-0000-4000-8000-{len(self.pairs) + 1:012d}",
            "kind": "blind_match",
            "institution_id": institution,
            "status": "open",
            "created_at": datetime.now(UTC),
        }
        self.pairs[key] = row
        return FakeCursor(row)


def test_rescan_opens_one_case_per_pair(monkeypatch):
    audits = []
    monkeypatch.setattr(bm.audit_store, "append_event", lambda *a, **k: audits.append(a))
    a = candidate(sid(1), "Aarav Sharma", INST_A)
    b = candidate(sid(2), "Aarav Sharmaa", INST_B)
    conn = FakeConn()
    created, events = bm._open_cases(conn, bm.find_matches([a, b], 0.85))
    assert len(created) == 1 and len(audits) == 1
    assert events[0][0] == "review_case.created"
    assert set(events[0][1]) == {"case_id", "kind", "institution_id", "status", "created_at"}
    again, again_events = bm._open_cases(conn, bm.find_matches([b, a], 0.85))
    assert (again, again_events) == ([], [])
    assert len(conn.pairs) == 1 and len(audits) == 1


# ---------------------------------------------------------------------------- reading
ROW = {
    "id": "60000000-0000-4000-8000-000000000009",
    "status": "open",
    "created_at": datetime(2026, 9, 2, tzinfo=UTC),
    "institution_a_name": "Institute A",
    "institution_b_name": "Institute B",
    "name_a": "Aarav Sharma",
    "dob_a": DOB,
    "name_b": "Aarav Sharmaa",
    "dob_b": DOB,
    "evidence": {
        "pair_key": f"{sid(1)}:{sid(2)}",
        "student_a_id": sid(1),
        "student_b_id": sid(2),
        "institution_a_id": INST_A,
        "institution_b_id": INST_B,
        "programme_a": "UG-CSE",
        "academic_year_a": "2026-27",
        "programme_b": "UG-ME",
        "academic_year_b": "2026-27",
        "dice": 0.912,
        "matched_on": ["name", "dob", "guardian"],
    },
}


def test_case_view_for_aicte_shows_both_sides_and_masked_hints():
    view = bm.case_view(ROW, User(id="x", role="aicte_admin"))
    assert (view["institution_a_name"], view["institution_b_name"]) == (
        "Institute A",
        "Institute B",
    )
    assert view["identity_hint_a"] == "A. S., 2008"
    assert "Aarav" not in json.dumps(view, default=str)


def test_case_view_for_institution_hides_the_other_side():
    view = bm.case_view(ROW, User(id="x", role="institution_admin", institution_id=INST_B))
    assert view["institution_b_id"] == INST_B and view["record_b"] == sid(2)
    assert view["institution_a_id"] == bm.HIDDEN and view["record_a"] == bm.HIDDEN
    assert view["institution_a_name"] is None
    assert view["identity_hint_a"] is None and view["identity_hint_b"] is None


def test_fixture_cases_are_scoped_for_institution_users(client):
    narmada = "10000000-0000-4000-8000-000000000002"
    everyone = client.get("/blind-match/cases", headers=as_role("auditor")).json()
    assert len(everyone) == 2
    mine = client.get("/blind-match/cases", headers=as_role("institution_admin", narmada)).json()
    assert len(mine) == 1
    assert mine[0]["institution_b_id"] == narmada
    assert mine[0]["institution_a_id"] == bm.HIDDEN and mine[0]["record_a"] == bm.HIDDEN
    assert client.get("/blind-match/cases", headers=as_role("student")).status_code == 403


def test_scan_requires_aicte_admin(client):
    assert client.post("/admin/blind-match/scan", headers=as_role("auditor")).status_code == 403
    ok = client.post("/admin/blind-match/scan", headers=as_role("aicte_admin"))
    assert ok.status_code == 200 and ok.json()["cases_created"] == []


# ---------------------------------------------------------------------------- upload hook
def test_upload_hook_skips_block_of_valid_apaar_rows(monkeypatch):
    import engine.blind_match.encoder as encoder

    from app.services.ingestion import NormalizedRow
    from app.services.validation import _fuzzy_findings

    calls = []
    monkeypatch.setattr(encoder, "encode_identity", lambda *a, **k: calls.append(a) or bytes(128))

    def row(n, apaar):
        values = {"student_name": f"Student {n}", "dob": DOB, "apaar_id": apaar}
        return NormalizedRow(row_number=n, values=values)

    from collections import Counter

    rows = [row(1, "999900000001"), row(2, "999900000002")]
    assert _fuzzy_findings(rows, SECRET, 0.85, 200, Counter()) == []
    assert calls == []
    _fuzzy_findings([*rows, row(3, "")], SECRET, 0.85, 200, Counter())
    assert len(calls) == 3


@pytest.mark.parametrize(("name", "dob", "hint"), [("aarav kumar sharma", DOB, "A. K. S., 2008")])
def test_identity_hint(name, dob, hint):
    assert bm.identity_hint(name, dob) == hint
    assert bm.identity_hint(None, dob) is None
