# Owner: Dev B
import random
import time
from datetime import UTC, date, datetime, timedelta

import pytest

from app.core.rule_codes import RuleCode
from app.services.ingestion import TEMPLATE_COLUMNS, NormalizedRow, normalize_row
from app.services.validation import (
    ValidationContext,
    count_findings,
    dob_block_key,
    engine_findings,
    error_rows,
    validate_rows,
)

SECRET = "test-pseudonym-secret"
BASE = {
    "institution_aicte_code": "1-9999003",
    "programme_code": "UG-CSE",
    "academic_year": "2026-27",
    "student_name": "aarav sharma",
    "dob": "2008-03-14",
    "gender": "male",
    "category": "general",
    "pwd": "false",
    "apaar_id": "999912340001",
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
    "qualifying_exam_pct": "92.4",
    "domicile_state": "Uttar Pradesh",
    "contact_phone": "+919800000001",
    "contact_email": "aarav@example.com",
    "guardian_name": "rakesh sharma",
}
IDENTITY = {c: c for c in TEMPLATE_COLUMNS}


def row(n: int = 1, **overrides: str):
    raw = {**BASE, **overrides}
    return normalize_row(raw, IDENTITY, n, SECRET)


def ctx(run_engine_hooks: bool = False, **kwargs) -> ValidationContext:
    defaults = {
        "cutoff": date(2026, 9, 30),
        "shared_contact_threshold": 5,
        "institution_code": "1-9999003",
        "programme_codes": {"UG-CSE", "UG-CE"},
        "run_engine_hooks": run_engine_hooks,
    }
    return ValidationContext(**{**defaults, **kwargs})


def codes(rows, context=None) -> set[RuleCode]:
    return {f.rule_code for f in validate_rows(rows, context or ctx())}


def test_clean_row_has_no_findings():
    assert codes([row()]) == set()


# ---------------------------------------------------------------- one test per rule
@pytest.mark.parametrize("column", ["student_name", "dob", "seat_pool", "qualifying_exam"])
def test_required_field_missing(column):
    findings = validate_rows([row(**{column: ""})], ctx())
    assert any(
        f.rule_code is RuleCode.REQUIRED_FIELD_MISSING and f.evidence["field"] == column
        for f in findings
    )


def test_required_field_invalid_enum_and_boolean():
    findings = validate_rows([row(gender="robot", pwd="maybe")], ctx())
    fields = {
        f.evidence["field"] for f in findings if f.rule_code is RuleCode.REQUIRED_FIELD_MISSING
    }
    assert fields == {"gender", "pwd"}


def test_apaar_missing():
    assert RuleCode.APAAR_MISSING in codes([row(apaar_id="")])
    assert RuleCode.APAAR_MISSING not in codes([row()])


def test_apaar_format():
    assert RuleCode.APAAR_FORMAT in codes([row(apaar_id="99991234567")])
    assert RuleCode.APAAR_FORMAT not in codes([row()])


def test_apaar_opted_out_is_info_not_error():
    rows = [row(apaar_id="", apaar_opt_out="yes", provisional_id="prov-1-9999003-0001")]
    findings = validate_rows(rows, ctx())
    assert {f.rule_code for f in findings} == {RuleCode.APAAR_OPTED_OUT}
    assert findings[0].severity == "info"
    assert error_rows(findings) == set()


def test_opted_out_without_provisional_id_is_an_error():
    findings = validate_rows([row(apaar_id="", apaar_opt_out="true")], ctx())
    assert any(f.evidence.get("field") == "provisional_id" for f in findings)


def test_dup_in_batch():
    rows = [row(1), row(2, student_name="Someone Else")]
    findings = validate_rows(rows, ctx())
    dup = [f for f in findings if f.rule_code is RuleCode.DUP_IN_BATCH]
    assert [(f.row_number, f.evidence["duplicate_of_row"]) for f in dup] == [(2, 1)]
    assert dup[0].evidence["apaar_id_masked"] == "XXXX-XXXX-0001"
    assert RuleCode.DUP_IN_BATCH not in codes([row(1), row(2, apaar_id="999912340002")])


def test_dup_cross_institution_uses_lookup():
    seen = []

    def lookup(ids):
        seen.append(ids)
        return {"999912340001": "1-9999002"}

    findings = validate_rows(
        [row(), row(2, apaar_id="999912340002")], ctx(cross_institution_lookup=lookup)
    )
    cross = [f for f in findings if f.rule_code is RuleCode.DUP_CROSS_INSTITUTION]
    assert [(f.row_number, f.evidence["other_institution_code"]) for f in cross] == [
        (1, "1-9999002")
    ]
    assert cross[0].severity == "review"
    assert seen == [["999912340001", "999912340002"]]
    assert RuleCode.DUP_CROSS_INSTITUTION not in codes(
        [row()], ctx(cross_institution_lookup=lambda ids: {})
    )


def test_dup_cross_institution_skipped_without_lookup():
    assert RuleCode.DUP_CROSS_INSTITUTION not in codes([row()], ctx())


def test_programme_unknown():
    assert RuleCode.PROGRAMME_UNKNOWN in codes([row(programme_code="UG-XYZ")])
    assert RuleCode.PROGRAMME_UNKNOWN not in codes([row(programme_code="ug-ce")])


def test_programme_unknown_for_other_institution_row():
    findings = validate_rows([row(institution_aicte_code="1-9999001")], ctx())
    assert [f.evidence.get("reason") for f in findings] == ["institution_mismatch"]


def test_pool_unknown():
    assert RuleCode.POOL_UNKNOWN in codes([row(seat_pool="vip")])
    assert RuleCode.POOL_UNKNOWN not in codes([row(seat_pool="TFW")])


def test_date_invalid():
    findings = validate_rows([row(dob="2008-02-30")], ctx())
    assert [f.rule_code for f in findings] == [RuleCode.DATE_INVALID]
    assert RuleCode.DATE_INVALID not in codes([row(dob="14/03/2008")])


def test_admission_after_cutoff():
    assert RuleCode.ADMISSION_AFTER_CUTOFF in codes([row(admission_date="2026-10-01")])
    assert RuleCode.ADMISSION_AFTER_CUTOFF not in codes([row(admission_date="2026-09-30")])


def test_fn_without_nationality():
    assert RuleCode.FN_WITHOUT_NATIONALITY in codes(
        [row(fn_status="true", seat_pool="fn_oci_pio", nationality="India")]
    )
    assert RuleCode.FN_WITHOUT_NATIONALITY not in codes(
        [row(fn_status="true", seat_pool="fn_oci_pio", nationality="NP")]
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"oci_status": "true", "nationality": "IN", "seat_pool": "fn_oci_pio"},
        {"oci_status": "true", "fn_status": "true", "nationality": "US", "seat_pool": "fn_oci_pio"},
        {"seat_pool": "fn_oci_pio"},
    ],
)
def test_oci_inconsistent(overrides):
    assert RuleCode.OCI_INCONSISTENT in codes([row(**overrides)])


def test_oci_consistent():
    assert RuleCode.OCI_INCONSISTENT not in codes(
        [row(oci_status="true", nationality="US", seat_pool="fn_oci_pio")]
    )


def test_nri_pool_mismatch():
    assert RuleCode.NRI_POOL_MISMATCH in codes([row(nri_category="true")])
    assert RuleCode.NRI_POOL_MISMATCH in codes([row(seat_pool="nri")])
    assert RuleCode.NRI_POOL_MISMATCH not in codes([row(nri_category="true", seat_pool="nri")])


@pytest.mark.parametrize("dob", ["2012-01-01", "1960-01-01"])
def test_age_implausible(dob):
    assert RuleCode.AGE_IMPLAUSIBLE in codes([row(dob=dob)])


def test_age_plausible_at_boundaries():
    assert RuleCode.AGE_IMPLAUSIBLE not in codes([row(dob="2011-08-05")])  # exactly 15


def test_shared_contact_cluster():
    shared = [
        row(n, apaar_id=f"9999123400{n:02d}", contact_email="desk@example.com") for n in range(1, 6)
    ]
    findings = validate_rows(shared, ctx())
    cluster = [f for f in findings if f.rule_code is RuleCode.SHARED_CONTACT_CLUSTER]
    assert sorted(f.row_number for f in cluster) == [1, 2, 3, 4, 5]
    assert all(f.evidence == {"cluster_size": 5} for f in cluster)
    assert RuleCode.SHARED_CONTACT_CLUSTER not in codes(shared[:4])


def test_shared_contact_cluster_respects_threshold():
    shared = [row(n, apaar_id=f"9999123400{n:02d}", contact_phone="9800000009") for n in (1, 2)]
    assert RuleCode.SHARED_CONTACT_CLUSTER in codes(shared, ctx(shared_contact_threshold=2))


# ---------------------------------------------------------------- engine hooks and totals
def test_engine_hooks_skip_while_not_implemented():
    assert codes([row()], ctx(run_engine_hooks=True)) == set()


def test_engine_signal_rows_become_findings(monkeypatch):
    import engine.signals.rules as rules
    from engine.types import Signal

    monkeypatch.setattr(
        rules,
        "backdating",
        lambda rows: [Signal("BACKDATED_ENTRY", "x", "review", {"row_numbers": [1]})],
    )
    findings = validate_rows([row()], ctx(run_engine_hooks=True))
    assert [(f.row_number, f.rule_code) for f in findings] == [(1, RuleCode.BACKDATED_ENTRY)]


def test_engine_rows_follow_the_contract(monkeypatch):
    import engine.signals.rules as rules

    seen = []
    monkeypatch.setattr(rules, "eligibility", lambda rows: seen.extend(rows) or [])
    validate_rows([row(1), row(2, apaar_id="999912340002", qualifying_exam_pct="")], ctx(True))
    today = datetime.now(UTC).date().isoformat()
    assert [r["row_number"] for r in seen] == [1, 2]
    assert set(seen[0]) == {"row_number", "upload_date", *TEMPLATE_COLUMNS}
    assert {r["upload_date"] for r in seen} == {today}
    assert (seen[0]["dob"], seen[0]["qualifying_exam_pct"]) == ("2008-03-14", 92.4)
    assert seen[1]["qualifying_exam_pct"] is None
    assert seen[0]["contact_phone"].startswith("hmac:")


def test_fake_engine_signals_become_findings(monkeypatch):
    import engine.signals.rules as rules

    from tests import fake_engine

    monkeypatch.setattr(rules, "eligibility", fake_engine.eligibility)
    monkeypatch.setattr(rules, "backdating", fake_engine.backdating)
    rows = [
        row(1),
        row(2, apaar_id="999912340002", qualifying_exam_pct="40"),
        row(3, apaar_id="999912340003", admission_date="2024-07-01", dob="2006-03-14"),
    ]
    findings = validate_rows(rows, ctx(True))
    assert [(f.row_number, f.rule_code) for f in findings] == [
        (2, RuleCode.QUALIFYING_BELOW_NORM),
        (3, RuleCode.BACKDATED_ENTRY),
    ]
    assert findings[0].severity == "warning" and findings[1].severity == "review"
    assert findings[0].evidence == {"reason": "Qualifying percentage below the AICTE minimum."}


def test_non_contract_signals_are_ignored_and_logged(monkeypatch, caplog):
    import engine.signals.rules as rules
    from engine.types import Signal

    good = {"row_numbers": [1], "reason": "ok"}
    monkeypatch.setattr(
        rules,
        "eligibility",
        lambda rows: [
            Signal("SOMETHING_ELSE", "x", "warning", good),
            Signal("QUALIFYING_BELOW_NORM", "x", "error", good),
            Signal("QUALIFYING_BELOW_NORM", "x", "warning", {"reason": "no rows"}),
            Signal("QUALIFYING_BELOW_NORM", "x", "warning", {"row_numbers": [99, "1"]}),
            {"code": "QUALIFYING_BELOW_NORM", "severity": "warning", "evidence": good},
            Signal("QUALIFYING_BELOW_NORM", "x", "warning", good),
        ],
    )
    with caplog.at_level("WARNING", logger="app.services.validation"):
        findings = validate_rows([row()], ctx(True))
    assert [(f.row_number, f.rule_code) for f in findings] == [(1, RuleCode.QUALIFYING_BELOW_NORM)]
    warnings = [r.getMessage() for r in caplog.records if "ignored" in r.getMessage()]
    assert len(warnings) == 1
    for reason in ("unknown_code", "unknown_severity", "missing_row_numbers"):
        assert reason in warnings[0]
    assert "'unknown_row_number': 2" in warnings[0]
    assert "Aarav" not in caplog.text and "999912340001" not in caplog.text


def test_engine_exception_does_not_break_validation(monkeypatch):
    import engine.blind_match.encoder as encoder
    import engine.signals.rules as rules

    def boom(*args, **kwargs):
        raise RuntimeError("engine bug")

    monkeypatch.setattr(rules, "eligibility", boom)
    monkeypatch.setattr(rules, "backdating", lambda rows: "not a list")
    monkeypatch.setattr(encoder, "encode_identity", boom)
    rows = [row(1, apaar_id="123")]
    findings = validate_rows(rows, ctx(True), blind_match_secret="s")
    assert {f.rule_code for f in findings} == {RuleCode.APAAR_FORMAT}


# ---------------------------------------------------------------- Blind Match hook
BM_SECRET = "test-blind-match-secret"


def fuzzy(findings):
    return sorted(
        (f.row_number, f.evidence["other_row"])
        for f in findings
        if f.rule_code is RuleCode.FUZZY_MATCH_CANDIDATE
    )


def opted(n: int, **overrides: str):
    values = {"apaar_id": "", "apaar_opt_out": "true", "provisional_id": f"P-{n}", **overrides}
    return row(n, **values)


def test_blind_match_matches_typo_variant_with_same_dob(fake_blind_match):
    rows = [row(1), opted(2, student_name="Aarav Sharme"), opted(3, student_name="Priya Nair")]
    findings = validate_rows(rows, ctx(True), blind_match_secret=BM_SECRET)
    assert fuzzy(findings) == [(2, 1)]
    match = next(f for f in findings if f.rule_code is RuleCode.FUZZY_MATCH_CANDIDATE)
    assert match.severity == "review" and 0.85 <= match.evidence["dice"] <= 1


def test_blind_match_blocks_same_name_different_dob(fake_blind_match):
    rows = [row(1), opted(2, dob="2008-03-15")]
    assert fuzzy(validate_rows(rows, ctx(True), blind_match_secret=BM_SECRET)) == []


def test_blind_match_never_pairs_distinct_valid_apaar_ids(fake_blind_match):
    rows = [row(1), row(2, apaar_id="999912340002")]
    assert fuzzy(validate_rows(rows, ctx(True), blind_match_secret=BM_SECRET)) == []


def test_blind_match_skips_same_id_pairs(fake_blind_match):
    # Same APAAR (valid or not) or same provisional ID is DUP_IN_BATCH, not a fuzzy match.
    for rows in (
        [row(1), row(2)],
        [row(1, apaar_id="123"), row(2, apaar_id="123")],
        [opted(1), opted(2, provisional_id="P-1")],
    ):
        assert fuzzy(validate_rows(rows, ctx(True), blind_match_secret=BM_SECRET)) == []


def test_blind_match_uses_threshold(fake_blind_match):
    rows = [row(1), opted(2, student_name="Aarav Sharme")]
    assert fuzzy(validate_rows(rows, ctx(True), blind_match_secret="k")) == [(2, 1)]
    strict = ctx(True, match_threshold=0.999)
    assert fuzzy(validate_rows(rows, strict, blind_match_secret="k")) == []


def test_blind_match_passes_bits_and_leaves_k_to_the_engine(monkeypatch):
    import engine.blind_match.encoder as encoder

    calls = []

    def spy(fields, secret, **kwargs):
        calls.append((fields, secret, kwargs))
        return bytes(128)

    monkeypatch.setattr(encoder, "encode_identity", spy)
    validate_rows([row(1), opted(2)], ctx(True), blind_match_secret=BM_SECRET)
    assert len(calls) == 2
    assert all(kwargs == {"bits": 1024} for _, _, kwargs in calls)
    assert calls[0][0] == {
        "student_name": "Aarav Sharma",
        "dob": "2008-03-14",
        "guardian_name": "Rakesh Sharma",
    }
    assert calls[0][1] == BM_SECRET.encode()


def test_blind_match_skipped_without_secret(monkeypatch, caplog):
    import engine.blind_match.encoder as encoder

    calls = []
    monkeypatch.setattr(encoder, "encode_identity", lambda *a, **k: calls.append(a))
    with caplog.at_level("WARNING", logger="app.services.validation"):
        validate_rows([row(1), opted(2)], ctx(True))
    assert calls == []
    assert "BLIND_MATCH_SECRET is empty" in caplog.text


def test_blind_match_block_key_is_keyed_full_dob():
    assert dob_block_key(date(2008, 3, 14), "a") == dob_block_key(date(2008, 3, 14), "a")
    assert dob_block_key(date(2008, 3, 14), "a") != dob_block_key(date(2008, 3, 15), "a")
    assert dob_block_key(date(2008, 3, 14), "a") != dob_block_key(date(2008, 3, 14), "b")


def test_blind_match_truncates_large_blocks(fake_blind_match, caplog):
    rows = [opted(n) for n in range(1, 6)]
    with caplog.at_level("WARNING", logger="app.services.validation"):
        findings = validate_rows(
            rows, ctx(True, blind_match_max_block=3), blind_match_secret=BM_SECRET
        )
    assert {f.evidence["other_row"] for f in findings if f.evidence.get("other_row")} <= {1, 2}
    assert max(f.row_number for f in findings if "other_row" in f.evidence) == 3
    assert "truncated 1 blocks to 3 rows" in caplog.text


def test_blind_match_20000_rows_is_fast(fake_blind_match):
    rng = random.Random(7)
    first = "Aarav Ananya Arjun Diya Ishaan Kavya Rohan Saanvi Vihaan Zara Dev Meera".split()
    last = "Sharma Patel Nair Iyer Gupta Reddy Khan Joshi Rao Singh Das Mehta".split()
    start = date(2006, 1, 1)
    rows = [
        NormalizedRow(
            n,
            {
                "student_name": f"{rng.choice(first)} {rng.choice(last)} {n}",
                "dob": start + timedelta(days=rng.randint(0, 3 * 365)),
                "guardian_name": f"{rng.choice(first)} {rng.choice(last)}",
                # No APAAR IDs: every pair in a block is compared (worst case).
                "apaar_id": None,
                "provisional_id": f"P-{n}",
            },
        )
        for n in range(1, 20001)
    ]
    started = time.perf_counter()
    engine_findings(rows, BM_SECRET)
    elapsed = time.perf_counter() - started
    print(f"Blind Match hook, 20000 rows: {elapsed:.2f}s")
    assert elapsed < 10


def test_error_rows_and_counts():
    rows = [
        row(1),
        row(2, apaar_id="123", contact_email="b@example.com"),
        row(3, apaar_id="", apaar_opt_out="true", provisional_id="P-1"),
    ]
    findings = validate_rows(rows, ctx())
    assert error_rows(findings) == {2}
    assert count_findings(3, findings) == {
        "rows_total": 3,
        "errors": 1,
        "warnings": 0,
        "review": 0,
        "info": 1,
    }


def test_evidence_never_holds_raw_contacts_or_full_apaar():
    rows = [row(n, contact_phone="+91 98000 00001") for n in range(1, 7)]
    text = repr([(f.message, f.evidence) for f in validate_rows(rows, ctx())])
    assert "9800000001" not in text
    assert "999912340001" not in text
