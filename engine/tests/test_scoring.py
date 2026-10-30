# Owner: Dev A
"""Comprehensive tests for Feature F17 Institution Integrity Scoring."""

from __future__ import annotations

from engine.scoring.calculator import IntegrityScoreCalculator, map_risk_level
from engine.scoring.integrity import integrity_score
from engine.scoring.service import IntegrityScoringService
from engine.scoring.weights import ScoringWeights
from engine.types import AnomalyResult, IntegrityScore, MatchCase, Signal


def test_clean_institution_max_score() -> None:
    calc = IntegrityScoreCalculator()
    score = calc.calculate(
        institution_id="inst-clean",
        signals=[],
        anomaly=0.0,
        blind_matches=[],
    )

    assert isinstance(score, IntegrityScore)
    assert score.institution_id == "inst-clean"
    assert score.score == 100.0
    assert score.risk_level == "low"
    assert score.components["total_deduction"] == 0.0
    assert len(score.signals) == 0


def test_deterministic_behaviour() -> None:
    signals = [
        Signal(institution_id="inst-1", signal_name="ELIGIBILITY_VIOLATION", severity="error"),
        Signal(institution_id="inst-1", signal_name="SHARED_CONTACT", severity="review"),
    ]
    anomaly = AnomalyResult(institution_id="inst-1", score=0.65)
    matches = [
        MatchCase(
            institution_a="inst-1",
            institution_b="inst-2",
            student_a_id="s1",
            student_b_id="s2",
            similarity_score=0.95,
            confidence=0.90,
        )
    ]

    calc = IntegrityScoreCalculator()
    res1 = calc.calculate("inst-1", signals=signals, anomaly=anomaly, blind_matches=matches)
    res2 = calc.calculate("inst-1", signals=signals, anomaly=anomaly, blind_matches=matches)

    assert res1.score == res2.score
    assert res1.risk_level == res2.risk_level
    assert res1.components == res2.components


def test_configurable_weights_and_deductions() -> None:
    signals = [
        Signal(institution_id="inst-2", signal_name="BACKDATED", severity="error"),
    ]
    anomaly = 0.50  # 50% anomaly
    matches = [
        MatchCase(
            institution_a="inst-2",
            institution_b="inst-3",
            student_a_id="s1",
            student_b_id="s3",
            similarity_score=1.0,
            confidence=1.0,
        )
    ]

    # Custom weights with known parameters:
    # signal_weight: 0.5, error penalty: 30.0 -> signal_deduction: 0.5 * 30.0 = 15.0
    # anomaly_weight: 0.3, max_anomaly_penalty: 100.0 -> anomaly_deduction: 0.3 * (0.5 * 100) = 15.0
    # blind_match_weight: 0.2, base_penalty: 50.0 -> bm_deduction: 0.2 * (50.0 * 1.0) = 10.0
    # Total deduction: 15.0 + 15.0 + 10.0 = 40.0
    # Expected score: 100.0 - 40.0 = 60.0
    weights = ScoringWeights(
        signal_weight=0.5,
        anomaly_weight=0.3,
        blind_match_weight=0.2,
        severity_weights={"error": 30.0, "review": 15.0, "warning": 8.0, "info": 2.0},
        blind_match_base_penalty=50.0,
    )

    calc = IntegrityScoreCalculator(weights=weights)
    score = calc.calculate("inst-2", signals=signals, anomaly=anomaly, blind_matches=matches)

    assert score.components["signals_deduction"] == 15.0
    assert score.components["anomaly_deduction"] == 15.0
    assert score.components["blind_match_deduction"] == 10.0
    assert score.components["total_deduction"] == 40.0
    assert score.score == 60.0


def test_signal_severity_hierarchy() -> None:
    calc = IntegrityScoreCalculator()

    # Calculate deduction for 1 error vs 1 warning
    err_score = calc.calculate(
        "inst-err",
        signals=[Signal(institution_id="inst-err", signal_name="RULE", severity="error")],
    )
    warn_score = calc.calculate(
        "inst-warn",
        signals=[Signal(institution_id="inst-warn", signal_name="RULE", severity="warning")],
    )

    # Error deduction should be strictly greater than warning deduction
    assert err_score.components["signals_deduction"] > warn_score.components["signals_deduction"]
    assert err_score.score < warn_score.score


def test_score_clamping_bounds() -> None:
    calc = IntegrityScoreCalculator()

    # Massive signals and anomaly to force negative score without clamping
    huge_signals = [
        Signal(institution_id="inst-worst", signal_name=f"RULE_{i}", severity="error")
        for i in range(50)
    ]
    worst_score = calc.calculate(
        "inst-worst",
        signals=huge_signals,
        anomaly=1.0,
        blind_matches=[
            MatchCase(
                institution_a="inst-worst",
                institution_b=f"inst-{i}",
                student_a_id=f"sa_{i}",
                student_b_id=f"sb_{i}",
                similarity_score=1.0,
                confidence=1.0,
            )
            for i in range(20)
        ],
    )

    # Clamped to >= 0.0
    assert worst_score.score == 0.0
    assert worst_score.risk_level == "critical"


def test_risk_level_mapping_and_thresholds() -> None:
    weights = ScoringWeights(
        threshold_low=80.0,
        threshold_medium=60.0,
        threshold_high=40.0,
    )

    # Lowercase
    assert map_risk_level(95.0, weights=weights) == "low"
    assert map_risk_level(80.0, weights=weights) == "low"
    assert map_risk_level(79.9, weights=weights) == "medium"
    assert map_risk_level(60.0, weights=weights) == "medium"
    assert map_risk_level(59.9, weights=weights) == "high"
    assert map_risk_level(40.0, weights=weights) == "high"
    assert map_risk_level(39.9, weights=weights) == "critical"
    assert map_risk_level(0.0, weights=weights) == "critical"

    # Title-case option
    assert map_risk_level(85.0, weights=weights, title_case=True) == "Low"
    assert map_risk_level(65.0, weights=weights, title_case=True) == "Medium"
    assert map_risk_level(45.0, weights=weights, title_case=True) == "High"
    assert map_risk_level(25.0, weights=weights, title_case=True) == "Critical"


def test_service_calculate_from_data_and_batch() -> None:
    service = IntegrityScoringService()

    data = {
        "institution_id": "inst-bundle",
        "signals": [
            {
                "signal_name": "ELIGIBILITY_VIOLATION",
                "severity": "review",
                "score": 60.0,
            }
        ],
        "anomaly_score": 0.45,
    }

    score = service.calculate_from_data(data)
    assert score.institution_id == "inst-bundle"
    assert 0.0 <= score.score <= 100.0
    assert len(score.signals) == 1

    batch = [
        {"institution_id": "inst-a", "anomaly_score": 0.1},
        {"institution_id": "inst-b", "anomaly_score": 0.9},
    ]
    scores = service.calculate_batch(batch)
    assert len(scores) == 2
    assert scores[0].institution_id == "inst-a"
    assert scores[1].institution_id == "inst-b"
    assert scores[0].score > scores[1].score


def test_backward_compatible_integrity_score_function() -> None:
    sig = Signal(institution_id="inst-compat", signal_name="TEST_SIGNAL", severity="warning")
    anomaly = AnomalyResult(institution_id="inst-compat", score=0.25)

    score = integrity_score([sig], anomaly)
    assert isinstance(score, IntegrityScore)
    assert score.institution_id == "inst-compat"
    assert score.score > 0.0
    assert len(score.signals) == 1
