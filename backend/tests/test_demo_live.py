# Owner: Dev B
"""The live demo file deck/demo/shadow-late-batch.csv and the Shadow Blind Match pair,
without a database: validation results, Seat Ledger effect and Blind Match with the fake
encoder."""

from collections import Counter
from datetime import UTC, date, datetime

import pytest

from app.core.config import Settings
from app.services import blind_match as bm
from app.services.ingestion import TEMPLATE_COLUMNS, parse_upload, suggest_mapping
from app.services.validation import dob_block_key
from scripts import demo_live_reset
from scripts.load_demo import (
    MEGHDOOT,
    MEGHDOOT_PLAN,
    NARMADA,
    NARMADA_PLAN,
    SHADOW,
    SHADOW_STORY,
    Scripted,
    misspell,
    shadow_rows,
)
from tests import fake_engine
from tests.test_demo_flows import _validate

SECRET = "unit-test-secret"
LIVE = demo_live_reset.LIVE_CSV


@pytest.fixture
def narmada():
    gen = Scripted(42, set())
    gen.clean(MEGHDOOT, MEGHDOOT_PLAN, block=1)
    rows = gen.clean(NARMADA, NARMADA_PLAN, block=2)
    twins = [r for r in rows if r["programme_code"] == "UG-CSE" and r["seat_pool"] == "regular"]
    return gen, rows, twins


@pytest.fixture
def live():
    settings = Settings()
    parsed = parse_upload(
        LIVE.name,
        LIVE.read_bytes(),
        max_mb=settings.max_upload_mb,
        max_rows=settings.max_upload_rows,
    )
    return parsed


def candidates(rows, institution, start):
    """bm.Candidate per row, ids numbered from ``start`` so pairs sort predictably."""
    out = []
    for n, row in enumerate(rows, start=start):
        dob = date.fromisoformat(row["dob"])
        fields = bm.identity_fields(row["student_name"], dob, row["guardian_name"])
        out.append(
            bm.Candidate(
                student_id=f"40000000-0000-4000-8000-{n:012d}",
                block=dob_block_key(dob, SECRET),
                bloom=fake_engine.encode_identity(fields, SECRET.encode(), bits=1024),
                apaar_id=row["apaar_id"] or None,
                provisional_id=row["provisional_id"] or None,
                has_guardian=bool(row["guardian_name"]),
                placements=(
                    bm.Placement(
                        institution, row["programme_code"], row["academic_year"],
                        datetime(2026, 8, 1, tzinfo=UTC),
                    ),
                ),
            )
        )  # fmt: skip
    return out


# ---------------------------------------------------------------------------- the CSV
def test_live_csv_uses_the_template_columns(live):
    assert live.headers == list(TEMPLATE_COLUMNS)
    assert len(live.rows) == 3
    assert suggest_mapping(live.headers).missing_required == []


def test_live_csv_rows_are_all_valid_with_no_findings(fake_blind_match, live, narmada):
    _, _, twins = narmada
    # Narmada's APAAR IDs as "elsewhere": none of the three rows reuses one.
    rows, findings = _validate(
        live.rows, "1-9999003", {"UG-CSE", "UG-CE"}, {t["apaar_id"] for t in twins}
    )
    assert len(rows) == 3
    assert findings == []


def test_live_csv_adds_three_to_the_shadow_regular_pool(live):
    assert {r["institution_aicte_code"] for r in live.rows} == {"1-9999003"}
    assert Counter(
        (r["programme_code"], r["academic_year"], r["seat_pool"]) for r in live.rows
    ) == {("UG-CSE", "2026-27", "regular"): 3}
    # 62 regular against 51 seats after the load; the live file takes it to 14 over.
    assert 62 + len(live.rows) - 51 == SHADOW_STORY["overrun_by"] + 3


def test_live_csv_misspells_a_different_narmada_student(live, narmada):
    _, _, twins = narmada
    source = twins[6]
    [copy] = [r for r in live.rows if r["student_name"] == misspell(source["student_name"])]
    assert (copy["dob"], copy["guardian_name"]) == (source["dob"], source["guardian_name"])
    assert copy["apaar_id"] != source["apaar_id"] and len(copy["apaar_id"]) == 12
    # Not the Narmada students load_demo already reuses in the Shadow batch.
    assert source not in twins[3:6]
    # No row shares an APAAR with the scripted (9999...) or datagen (9999...) ranges.
    assert all(not r["apaar_id"].startswith("9999") for r in live.rows)


def test_live_csv_opens_exactly_one_blind_match_case_with_narmada(fake_blind_match, live, narmada):
    gen, rows, twins = narmada
    shadow = [r for r in shadow_rows(gen, twins[3:5], twins[5]) if r["student_name"]]
    pool = candidates(rows, NARMADA, 1) + candidates(shadow, SHADOW, 1000)
    before = bm.find_matches(pool, 0.85)
    after = bm.find_matches(pool + candidates(live.rows, SHADOW, 2000), 0.85)
    new = [m for m in after if m.pair_key not in {b.pair_key for b in before}]
    assert len(new) == 1
    [match] = new
    assert {match.place_a.institution_id, match.place_b.institution_id} == {SHADOW, NARMADA}


# ---------------------------------------------------------------------------- load_demo
def test_shadow_batch_has_one_blind_match_pair_with_narmada(fake_blind_match, narmada):
    gen, rows, twins = narmada
    shadow = shadow_rows(gen, twins[3:5], twins[5])
    typo = [r for r in shadow if r["student_name"] == misspell(twins[5]["student_name"])]
    assert len(typo) == 1 and typo[0]["apaar_id"] != twins[5]["apaar_id"]
    assert (typo[0]["dob"], typo[0]["guardian_name"]) == (
        twins[5]["dob"],
        twins[5]["guardian_name"],
    )
    valid = [r for r in shadow if r["student_name"]]
    matches = bm.find_matches(candidates(rows, NARMADA, 1) + candidates(valid, SHADOW, 1000), 0.85)
    # Same-APAAR twins are one student (DUP_CROSS_INSTITUTION), not a Blind Match pair.
    assert len(matches) == SHADOW_STORY["blind_match_with_narmada"] == 1


# ---------------------------------------------------------------------------- reset script
def test_reset_refuses_without_a_database(monkeypatch, capsys):
    monkeypatch.setattr(demo_live_reset, "get_settings", lambda: Settings(database_url=""))
    assert demo_live_reset.main(["--yes"]) == 2
    assert "DATABASE_URL" in capsys.readouterr().out


def test_reset_file_is_the_demo_csv():
    assert LIVE.name == "shadow-late-batch.csv" and LIVE.exists()
