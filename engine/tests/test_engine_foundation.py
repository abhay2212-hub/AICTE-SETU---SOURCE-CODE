# Owner: Dev A
from datetime import datetime

from engine.config import MATCH_THRESHOLD, MODEL_VERSION
from engine.types import IntegrityScore, MatchCase, Signal


def test_config_defaults() -> None:
    assert isinstance(MATCH_THRESHOLD, float)
    assert MATCH_THRESHOLD == 0.85
    assert isinstance(MODEL_VERSION, str)
    assert MODEL_VERSION == "0.1.0"


def test_match_case_creation() -> None:
    case = MatchCase(
        institution_a="inst-001",
        institution_b="inst-002",
        student_a_id="stud-001",
        student_b_id="stud-002",
        similarity_score=0.92,
        confidence=0.88,
        matched_fields=["name", "dob"],
        status="open",
    )
    assert case.institution_a == "inst-001"
    assert case.similarity_score == 0.92
    assert case.case_id is not None
    assert isinstance(case.created_at, datetime)


def test_signal_compatibility() -> None:
    # Legacy-style positional / keyword arguments
    sig1 = Signal(
        code="ELIGIBILITY_FAIL",
        institution_id="inst-001",
        severity="error",
        evidence={"pct": 45.0},
    )
    assert sig1.code == "ELIGIBILITY_FAIL"
    assert sig1.signal_name == "ELIGIBILITY_FAIL"
    assert sig1.signal_id is not None

    # New-style fields
    sig2 = Signal(
        institution_id="inst-002",
        signal_name="DUP_ENROLMENT",
        severity="error",
        score=75.0,
        evidence={"pair": ["s1", "s2"]},
        description="Cross-institution duplicate detected",
    )
    assert sig2.signal_name == "DUP_ENROLMENT"
    assert sig2.code == "DUP_ENROLMENT"
    assert sig2.score == 75.0


def test_integrity_score_fields() -> None:
    sig = Signal(institution_id="inst-001", signal_name="INTAKE_OVERRUN", severity="review")
    score = IntegrityScore(
        institution_id="inst-001",
        score=82.5,
        risk_level="low",
        signals=[sig],
        components={"rules": 10.0, "anomaly": 7.5},
    )
    assert score.score == 82.5
    assert score.risk_level == "low"
    assert len(score.signals) == 1
    assert score.components["rules"] == 10.0
