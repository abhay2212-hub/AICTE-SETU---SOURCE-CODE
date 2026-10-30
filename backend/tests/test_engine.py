# Owner: Dev A
from datetime import datetime

from app.core.config import Settings
from app.models.engine import IntegrityScore, MatchCase, Signal


def test_engine_info_endpoint(client):
    response = client.get("/engine")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Integrity Intelligence Engine"
    assert data["status"] == "active"
    assert "version" in data
    assert "match_threshold" in data
    assert "model_version" in data


def test_engine_health_endpoint(client):
    response = client.get("/engine/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["engine_ok"] is True
    assert "version" in data


def test_settings_engine_defaults():
    settings = Settings()
    assert settings.match_threshold == 0.85
    assert settings.model_version == "0.1.0"


def test_match_case_pydantic_model():
    case = MatchCase(
        institution_a="inst-a",
        institution_b="inst-b",
        student_a_id="stud-a",
        student_b_id="stud-b",
        similarity_score=0.95,
        confidence=0.90,
        matched_fields=["name", "father_name", "dob"],
        status="open",
    )
    assert case.institution_a == "inst-a"
    assert case.similarity_score == 0.95
    assert case.confidence == 0.90
    assert case.case_id is not None
    assert isinstance(case.created_at, datetime)


def test_signal_pydantic_model():
    sig = Signal(
        institution_id="inst-a",
        signal_name="CROSS_INSTITUTION_DUPLICATE",
        severity="error",
        score=90.0,
        evidence={"details": "same student in two institutions"},
        description="Duplicate enrolment across institutions",
    )
    assert sig.institution_id == "inst-a"
    assert sig.signal_name == "CROSS_INSTITUTION_DUPLICATE"
    assert sig.severity == "error"
    assert sig.score == 90.0
    assert sig.signal_id is not None
    assert isinstance(sig.created_at, datetime)


def test_integrity_score_pydantic_model():
    sig = Signal(
        institution_id="inst-a",
        signal_name="INTAKE_OVERRUN",
        severity="review",
    )
    score = IntegrityScore(
        institution_id="inst-a",
        score=85.0,
        risk_level="medium",
        signals=[sig],
    )
    assert score.institution_id == "inst-a"
    assert score.score == 85.0
    assert score.risk_level == "medium"
    assert len(score.signals) == 1
    assert isinstance(score.generated_at, datetime)


def test_post_blind_match_api_exact_apaar(client, settings_override):
    settings_override(blind_match_secret="test-secret-key-32b-length-here!")
    payload = {
        "records": [
            {
                "student_id": "stud-1",
                "institution_id": "inst-1",
                "student_name": "Aarav Sharma",
                "dob": "2004-05-15",
                "apaar_id": "999900001111",
            },
            {
                "student_id": "stud-2",
                "institution_id": "inst-2",
                "student_name": "Aarav Sharma",
                "dob": "2004-05-15",
                "apaar_id": "999900001111",
            },
        ]
    }
    response = client.post("/engine/blind-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    match = data[0]
    assert match["institution_a"] == "inst-1"
    assert match["institution_b"] == "inst-2"
    assert match["similarity_score"] == 1.0
    assert match["confidence"] == 1.0
    assert "apaar_id" in match["matched_fields"]


def test_post_blind_match_api_fuzzy_matching(client, settings_override):
    settings_override(blind_match_secret="test-secret-key-32b-length-here!")
    payload = {
        "records": [
            {
                "student_id": "stud-a",
                "institution_id": "inst-1",
                "student_name": "Priyanka Joshi",
                "dob": "2004-07-20",
                "father_name": "Kailash Joshi",
                "mother_name": "Meena Joshi",
            },
            {
                "student_id": "stud-b",
                "institution_id": "inst-2",
                "student_name": "Priyanka Joshi",
                "dob": "2004-07-20",
                "father_name": "Kailash Joshi",
                "mother_name": "Meena Joshi",
            },
            {
                "student_id": "stud-c",
                "institution_id": "inst-3",
                "student_name": "Harsh Patel",
                "dob": "2004-07-20",
                "father_name": "Nitin Patel",
                "mother_name": "Rita Patel",
            },
        ],
        "threshold": 0.85,
    }
    response = client.post("/engine/blind-match", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["student_a_id"] == "stud-a"
    assert data[0]["student_b_id"] == "stud-b"
    assert data[0]["similarity_score"] >= 0.85


def test_post_blind_match_api_direct_list(client, settings_override):
    settings_override(blind_match_secret="test-secret-key-32b-length-here!")
    records = [
        {
            "student_id": "stud-x",
            "institution_id": "inst-1",
            "student_name": "Vikram Seth",
            "dob": "2004-03-12",
            "apaar_id": "999955554444",
        },
        {
            "student_id": "stud-y",
            "institution_id": "inst-2",
            "student_name": "Vikram Seth",
            "dob": "2004-03-12",
            "apaar_id": "999955554444",
        },
    ]
    response = client.post("/engine/blind-match", json=records)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_post_signals_api_eligibility(client):
    payload = {
        "admissions": [
            {
                "student_id": "stud-violator",
                "institution_id": "inst-test",
                "programme_code": "BTECH_CSE",
                "category": "general",
                "qualifying_exam_pct": 35.0,  # Below 45% norm
                "dob": "2005-01-01",
                "admission_date": "2023-08-01",
            }
        ]
    }
    response = client.post("/engine/signals", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    sig = data[0]
    assert sig["institution_id"] == "inst-test"
    assert sig["signal_name"] == "ELIGIBILITY_VIOLATION"
    assert sig["score"] >= 70.0
    assert "evidence" in sig
    assert sig["evidence"]["violated_rule"] == "QUALIFYING_BELOW_NORM"


def test_post_signals_api_shared_contacts(client):
    payload = {
        "records": [
            {
                "student_id": "s1",
                "institution_id": "inst-1",
                "contact_phone": "9876543210",
            },
            {
                "student_id": "s2",
                "institution_id": "inst-2",
                "contact_phone": "9876543210",
            },
        ]
    }
    response = client.post("/engine/signals", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(s["signal_name"] == "SHARED_CONTACT_CLUSTER" for s in data)


def test_post_signals_api_backdated(client):
    payload = {
        "admissions": [
            {
                "student_id": "s-delayed",
                "institution_id": "inst-delay",
                "admission_date": "2023-01-01",
                "upload_date": "2023-04-15",
            }
        ]
    }
    response = client.post("/engine/signals", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["signal_name"] == "BACKDATED_ADMISSIONS"
    assert data[0]["evidence"]["delay"] > 30


def test_post_signals_api_zero_attrition(client):
    payload = {
        "historical_stats": [
            {
                "institution_id": "inst-full",
                "academic_year": "2021-22",
                "approved_seats": 100,
                "enrolled_students": 100,
                "attrition_count": 0,
            },
            {
                "institution_id": "inst-full",
                "academic_year": "2022-23",
                "approved_seats": 100,
                "enrolled_students": 100,
                "attrition_count": 0,
            },
        ]
    }
    response = client.post("/engine/signals", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["signal_name"] == "ZERO_ATTRITION_CAP_FILLING"
    assert data[0]["evidence"]["utilisation"] == 1.0


def test_post_signals_api_clean_admissions(client):
    payload = {
        "admissions": [
            {
                "student_id": "s-clean",
                "institution_id": "inst-clean",
                "programme_code": "BTECH",
                "category": "general",
                "qualifying_exam_pct": 78.0,
                "seat_pool": "regular",
                "dob": "2005-01-01",
                "admission_date": "2023-08-01",
                "upload_date": "2023-08-05",
                "contact_phone": "9998881111",
            }
        ]
    }
    response = client.post("/engine/signals", json=payload)
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_post_signals_api_empty_and_direct_list(client):
    # Empty payload
    res1 = client.post("/engine/signals", json={})
    assert res1.status_code == 200
    assert res1.json() == []

    # Direct list input
    res2 = client.post("/engine/signals", json=[])
    assert res2.status_code == 200
    assert res2.json() == []


def test_post_anomaly_api(client):
    payload = {
        "institutions": [
            {
                "institution_id": f"inst-{i}",
                "seat_utilisation": 0.8,
                "duplicate_rate": 0.01,
            }
            for i in range(10)
        ]
        + [
            {
                "institution_id": "inst-extreme",
                "seat_utilisation": 2.5,
                "duplicate_rate": 0.8,
                "backdated_admission_rate": 0.9,
            }
        ]
    }
    response = client.post("/engine/anomaly", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 11
    outlier = next(r for r in data if r["institution_id"] == "inst-extreme")
    assert outlier["prediction"] == "anomalous"
    assert outlier["score"] > 0.5


def test_post_integrity_score_api(client):
    payload = {
        "institution_id": "inst-score-test",
        "signals": [
            {
                "signal_name": "ELIGIBILITY_VIOLATION",
                "severity": "review",
                "score": 75.0,
            }
        ],
        "anomaly_score": 0.40,
    }
    response = client.post("/engine/integrity-score", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["institution_id"] == "inst-score-test"
    assert 0.0 <= data["score"] <= 100.0
    assert data["risk_level"] in ("low", "medium", "high", "critical")
    assert "components" in data


def test_post_evaluate_api(client):
    response = client.post("/engine/evaluate", json={})
    assert response.status_code == 200
    data = response.json()
    assert "blind_match" in data
    assert "signals" in data
    assert "anomaly_detection" in data
    assert "integrity_score" in data
    assert "benchmark" in data
    assert "summary" in data
    assert data["summary"]["status"] == "completed"


def test_engine_router_role_guard(client):
    # aicte_admin is allowed
    res_admin = client.get("/engine", headers={"X-Demo-Role": "aicte_admin"})
    assert res_admin.status_code == 200

    # Non-aicte_admin roles are rejected with 403 Forbidden
    res_inst = client.get("/engine", headers={"X-Demo-Role": "institution_admin"})
    assert res_inst.status_code == 403

    res_student = client.get("/engine", headers={"X-Demo-Role": "student"})
    assert res_student.status_code == 403


def test_engine_upload_hooks_findings():
    """Verify backend upload hooks for eligibility, backdating, and blind match."""
    from datetime import date

    from app.core.rule_codes import RuleCode
    from app.services.ingestion import NormalizedRow
    from app.services.validation import ValidationContext, validate_rows

    ctx = ValidationContext(cutoff=date(2026, 9, 30), run_engine_hooks=True)
    secret = "788bfbe5462dd04ff8a1c3ddda1207bf971d43e11e08d03119a5f753f5c9d268"

    # Row 1: Low qualifying percentage (38% for general -> below 45% norm)
    # Row 2: Backdated entry (admission Jan 1, upload March 1 -> delay 59 days > 30)
    # Row 3 & 4: Ishita Chaudhary with DIFFERENT DOBs (2008-09-11 vs 2008-03-09) -> should NOT match
    # Row 5 & 6: Same person with name typo + same DOB -> SHOULD match
    rows = [
        NormalizedRow(
            row_number=1,
            values={
                "institution_aicte_code": "1-001",
                "programme_code": "BTECH",
                "academic_year": "2026-27",
                "student_name": "Student Below Norm",
                "dob": date(2005, 5, 10),
                "gender": "male",
                "category": "general",
                "pwd": False,
                "apaar_id": "111122223331",
                "apaar_opt_out": False,
                "nationality": "Indian",
                "oci_status": False,
                "fn_status": False,
                "nri_category": False,
                "seat_pool": "regular",
                "admission_mode": "cap",
                "admission_date": date(2026, 8, 1),
                "qualifying_exam": "12th",
                "qualifying_exam_pct": 38.0,
                "domicile_state": "Delhi",
                "upload_date": "2026-08-05",
            },
        ),
        NormalizedRow(
            row_number=2,
            values={
                "institution_aicte_code": "1-001",
                "programme_code": "BTECH",
                "academic_year": "2026-27",
                "student_name": "Student Backdated",
                "dob": date(2005, 5, 10),
                "gender": "male",
                "category": "general",
                "pwd": False,
                "apaar_id": "111122223332",
                "apaar_opt_out": False,
                "nationality": "Indian",
                "oci_status": False,
                "fn_status": False,
                "nri_category": False,
                "seat_pool": "regular",
                "admission_mode": "cap",
                "admission_date": date(2026, 1, 1),
                "qualifying_exam": "12th",
                "qualifying_exam_pct": 75.0,
                "domicile_state": "Delhi",
                "upload_date": "2026-04-15",
            },
        ),
        NormalizedRow(
            row_number=3,
            values={
                "institution_aicte_code": "1-001",
                "programme_code": "BTECH",
                "academic_year": "2026-27",
                "student_name": "Ishita Chaudhary",
                "dob": date(2008, 9, 11),
                "gender": "female",
                "category": "general",
                "pwd": False,
                "apaar_id": "111122223333",
                "apaar_opt_out": False,
                "nationality": "Indian",
                "oci_status": False,
                "fn_status": False,
                "nri_category": False,
                "seat_pool": "regular",
                "admission_mode": "cap",
                "admission_date": date(2026, 8, 1),
                "qualifying_exam": "12th",
                "qualifying_exam_pct": 85.0,
                "domicile_state": "Delhi",
                "upload_date": "2026-08-05",
            },
        ),
        NormalizedRow(
            row_number=4,
            values={
                "institution_aicte_code": "1-001",
                "programme_code": "BTECH",
                "academic_year": "2026-27",
                "student_name": "Ishita Chaudhary",
                "dob": date(2008, 3, 9),
                "gender": "female",
                "category": "general",
                "pwd": False,
                "apaar_id": "111122223334",
                "apaar_opt_out": False,
                "nationality": "Indian",
                "oci_status": False,
                "fn_status": False,
                "nri_category": False,
                "seat_pool": "regular",
                "admission_mode": "cap",
                "admission_date": date(2026, 8, 1),
                "qualifying_exam": "12th",
                "qualifying_exam_pct": 85.0,
                "domicile_state": "Delhi",
                "upload_date": "2026-08-05",
            },
        ),
        NormalizedRow(
            row_number=5,
            values={
                "institution_aicte_code": "1-001",
                "programme_code": "BTECH",
                "academic_year": "2026-27",
                "student_name": "Rohan Gupta",
                "dob": date(2005, 7, 20),
                "gender": "male",
                "category": "general",
                "pwd": False,
                "apaar_id": "111122223335",
                "apaar_opt_out": False,
                "nationality": "Indian",
                "oci_status": False,
                "fn_status": False,
                "nri_category": False,
                "seat_pool": "regular",
                "admission_mode": "cap",
                "admission_date": date(2026, 8, 1),
                "qualifying_exam": "12th",
                "qualifying_exam_pct": 85.0,
                "domicile_state": "Delhi",
                "upload_date": "2026-08-05",
            },
        ),
        NormalizedRow(
            row_number=6,
            values={
                "institution_aicte_code": "1-001",
                "programme_code": "BTECH",
                "academic_year": "2026-27",
                "student_name": "Rohan Guptha",
                "dob": date(2005, 7, 20),
                "gender": "male",
                "category": "general",
                "pwd": False,
                "apaar_id": None,
                "apaar_opt_out": True,
                "provisional_id": "PROV-1-001-0006",
                "nationality": "Indian",
                "oci_status": False,
                "fn_status": False,
                "nri_category": False,
                "seat_pool": "regular",
                "admission_mode": "cap",
                "admission_date": date(2026, 8, 1),
                "qualifying_exam": "12th",
                "qualifying_exam_pct": 85.0,
                "domicile_state": "Delhi",
                "upload_date": "2026-08-05",
            },
        ),
    ]

    findings = validate_rows(rows, ctx, blind_match_secret=secret)

    # 1. QUALIFYING_BELOW_NORM on row 1
    norm_findings = [f for f in findings if f.rule_code == RuleCode.QUALIFYING_BELOW_NORM]
    assert len(norm_findings) == 1
    assert norm_findings[0].row_number == 1
    assert norm_findings[0].severity == "warning"

    # 2. BACKDATED_ENTRY on row 2
    backdate_findings = [f for f in findings if f.rule_code == RuleCode.BACKDATED_ENTRY]
    assert len(backdate_findings) == 1
    assert backdate_findings[0].row_number == 2
    assert backdate_findings[0].severity == "review"

    # 3. Fuzzy matches: Ishita Chaudhary (different DOB) should NOT be flagged
    # Rohan Gupta / Rohan Guptha (same DOB) SHOULD be flagged
    fuzzy_findings = [f for f in findings if f.rule_code == RuleCode.FUZZY_MATCH_CANDIDATE]
    assert len(fuzzy_findings) == 1
    assert fuzzy_findings[0].row_number == 6
    assert fuzzy_findings[0].evidence["other_row"] == 5
    assert fuzzy_findings[0].evidence["dice"] >= 0.85
