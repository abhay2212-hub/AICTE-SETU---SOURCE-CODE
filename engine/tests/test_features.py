# Owner: Dev A
"""Comprehensive tests for Feature F16 institution feature extraction."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from engine.anomaly.features import (
    FEATURE_NAMES,
    InstitutionFeatureExtractor,
    InstitutionFeatureVector,
    extract_institution_features,
)
from engine.types import InstitutionFeatures, MatchCase, Signal


def test_feature_vector_serialization() -> None:
    vec = InstitutionFeatureVector(
        institution_id="inst-001",
        seat_utilisation=0.95,
        intake_growth=0.12,
        duplicate_rate=0.03,
        blind_match_rate=0.04,
        shared_contact_rate=0.08,
        backdated_admission_rate=0.15,
        eligibility_violation_count=2.0,
        zero_attrition_frequency=0.5,
        average_signal_severity=3.0,
        total_signals_generated=4.0,
        extra_features={"custom_ratio": 1.25},
    )

    d = vec.to_dict()
    assert d["seat_utilisation"] == 0.95
    assert d["intake_growth"] == 0.12
    assert d["custom_ratio"] == 1.25
    assert len(d) == len(FEATURE_NAMES) + 1

    arr = vec.to_array()
    assert isinstance(arr, np.ndarray)
    assert arr.shape == (len(FEATURE_NAMES),)
    assert arr[0] == 0.95  # seat_utilisation is first in FEATURE_NAMES

    inst_feats = vec.to_institution_features()
    assert isinstance(inst_feats, InstitutionFeatures)
    assert inst_feats.institution_id == "inst-001"
    assert inst_feats.features["seat_utilisation"] == 0.95


def test_extractor_from_precomputed_dict() -> None:
    extractor = InstitutionFeatureExtractor()
    data = {
        "institution_id": "inst-101",
        "features": {
            "seat_utilisation": 0.88,
            "intake_growth": 0.05,
            "duplicate_rate": 0.01,
            "blind_match_rate": 0.02,
            "shared_contact_rate": 0.03,
            "backdated_admission_rate": 0.04,
            "eligibility_violation_count": 1.0,
            "zero_attrition_frequency": 0.0,
            "average_signal_severity": 2.0,
            "total_signals_generated": 1.0,
        },
    }
    vec = extractor.extract("inst-101", data)
    assert vec.institution_id == "inst-101"
    assert vec.seat_utilisation == 0.88
    assert vec.eligibility_violation_count == 1.0


def test_extractor_from_raw_admissions_and_history() -> None:
    extractor = InstitutionFeatureExtractor(backdated_threshold_days=30, qualifying_min_pct=45.0)

    admissions = [
        # Student 1: Below norm marks (violator), shared phone with student 2
        {
            "student_id": "s1",
            "institution_id": "inst-alpha",
            "qualifying_exam_pct": 38.0,
            "admission_date": "2023-08-01",
            "upload_date": "2023-08-05",
            "contact_phone": "9876543210",
            "apaar_id": "111122223333",
        },
        # Student 2: Backdated (>30 days delay), duplicate APAAR
        {
            "student_id": "s2",
            "institution_id": "inst-alpha",
            "qualifying_exam_pct": 65.0,
            "admission_date": "2023-01-10",
            "upload_date": "2023-04-15",
            "contact_phone": "9876543210",
            "apaar_id": "111122223333",
        },
    ]

    historical_stats = [
        {
            "institution_id": "inst-alpha",
            "academic_year": "2021-22",
            "approved_seats": 100,
            "enrolled_students": 100,
            "attrition_count": 0,
        },
        {
            "institution_id": "inst-alpha",
            "academic_year": "2022-23",
            "approved_seats": 100,
            "enrolled_students": 110,
            "attrition_count": 0,
        },
    ]

    signals = [
        Signal(
            institution_id="inst-alpha",
            signal_name="ELIGIBILITY_VIOLATION",
            severity="error",
        ),
        Signal(
            institution_id="inst-alpha",
            signal_name="BACKDATED_ADMISSIONS",
            severity="review",
        ),
    ]

    matches = [
        MatchCase(
            institution_a="inst-alpha",
            institution_b="inst-beta",
            student_a_id="s1",
            student_b_id="s9",
            similarity_score=0.92,
            confidence=0.90,
            created_at=datetime.now(UTC),
        )
    ]

    payload = {
        "admissions": admissions,
        "historical_stats": historical_stats,
        "signals": signals,
        "matches": matches,
    }

    vec = extractor.extract("inst-alpha", payload)

    assert vec.institution_id == "inst-alpha"
    # Latest enrolled (110) / approved (100) = 1.1
    assert vec.seat_utilisation == 1.1
    # Intake growth: (110 - 100) / 100 = 0.10
    assert vec.intake_growth == 0.10
    # Duplicate rate: 1 duplicate APAAR out of 2 = 0.50
    assert vec.duplicate_rate == 0.50
    # Blind match rate: 1 match case out of 2 admissions = 0.50
    assert vec.blind_match_rate == 0.50
    # Shared contact rate: 1 shared contact out of 2 admissions = 0.50
    assert vec.shared_contact_rate == 0.50
    # Backdated rate: 1 delayed admission out of 2 admissions = 0.50
    assert vec.backdated_admission_rate == 0.50
    # Eligibility violation count: 1 student below 45% norm = 1.0
    assert vec.eligibility_violation_count == 1.0
    # Zero attrition: 2 years with 0 attrition at >=100% capacity = 2/2 = 1.0
    assert vec.zero_attrition_frequency == 1.0
    # Signals: 2 total signals
    assert vec.total_signals_generated == 2.0
    # Severity: error (4.0) + review (3.0) = 7.0 / 2 = 3.5
    assert vec.average_signal_severity == 3.5


def test_extractor_handles_empty_and_zero_division() -> None:
    extractor = InstitutionFeatureExtractor()
    vec = extractor.extract("inst-empty", {})
    assert vec.institution_id == "inst-empty"
    assert vec.seat_utilisation == 0.0
    assert vec.intake_growth == 0.0
    assert vec.duplicate_rate == 0.0
    assert vec.total_signals_generated == 0.0


def test_convenience_function() -> None:
    vec = extract_institution_features("inst-func", {"seat_utilisation": 0.85})
    assert vec.institution_id == "inst-func"
    assert vec.seat_utilisation == 0.85
