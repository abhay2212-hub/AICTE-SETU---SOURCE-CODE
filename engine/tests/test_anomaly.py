# Owner: Dev A
"""Comprehensive tests for Feature F16 ML-based Institution Anomaly Detection."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pytest

from engine.anomaly.features import FEATURE_NAMES, InstitutionFeatureVector
from engine.anomaly.isolation import rank_institutions
from engine.anomaly.model import BaseAnomalyModel, IsolationForestModel
from engine.anomaly.service import AnomalyDetectionService
from engine.types import AnomalyResult, InstitutionFeatures


def _generate_synthetic_dataset(
    n_normal: int = 20, n_outliers: int = 3
) -> list[InstitutionFeatureVector]:
    dataset: list[InstitutionFeatureVector] = []
    # Normal institutions: typical metrics
    for i in range(n_normal):
        dataset.append(
            InstitutionFeatureVector(
                institution_id=f"inst-normal-{i}",
                seat_utilisation=0.75 + (i % 5) * 0.03,
                intake_growth=0.02 + (i % 3) * 0.01,
                duplicate_rate=0.01,
                blind_match_rate=0.01,
                shared_contact_rate=0.02,
                backdated_admission_rate=0.02,
                eligibility_violation_count=0.0,
                zero_attrition_frequency=0.0,
                average_signal_severity=1.0,
                total_signals_generated=1.0,
            )
        )

    # Outlier institutions: extreme metrics
    for j in range(n_outliers):
        dataset.append(
            InstitutionFeatureVector(
                institution_id=f"inst-outlier-{j}",
                seat_utilisation=1.85,
                intake_growth=0.95,
                duplicate_rate=0.45,
                blind_match_rate=0.50,
                shared_contact_rate=0.60,
                backdated_admission_rate=0.70,
                eligibility_violation_count=25.0,
                zero_attrition_frequency=1.0,
                average_signal_severity=4.0,
                total_signals_generated=15.0,
            )
        )
    return dataset


def test_isolation_forest_model_fit_and_predict() -> None:
    model = IsolationForestModel(contamination=0.15, random_state=42)
    X = np.array(
        [
            [0.7, 0.02, 0.01],
            [0.72, 0.03, 0.01],
            [0.71, 0.02, 0.02],
            [1.85, 0.95, 0.80],  # obvious outlier
        ]
    )
    model.fit(X, ["seat_utilisation", "intake_growth", "duplicate_rate"])

    preds = model.predict(X)
    scores = model.score_samples(X)

    assert len(preds) == 4
    # Outlier sample is last
    assert preds[-1] == -1
    assert preds[0] == 1
    # Scores bounded in [0.0, 1.0]
    for s in scores:
        assert 0.0 <= s <= 1.0
    # Outlier should have higher anomaly score than normal points
    assert scores[-1] > scores[0]


def test_deterministic_behaviour() -> None:
    dataset = _generate_synthetic_dataset(15, 2)

    service1 = AnomalyDetectionService(random_state=42)
    res1 = service1.fit_predict(dataset)

    service2 = AnomalyDetectionService(random_state=42)
    res2 = service2.fit_predict(dataset)

    assert len(res1) == len(res2)
    for r1, r2 in zip(res1, res2, strict=True):
        assert r1.institution_id == r2.institution_id
        assert r1.score == r2.score
        assert r1.prediction == r2.prediction
        assert r1.top_features == r2.top_features


def test_configurable_contamination(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANOMALY_CONTAMINATION", "0.25")
    # Instantiated without explicit contamination should load 0.25 from config
    model = IsolationForestModel(contamination=0.25, random_state=42)
    assert model.contamination == 0.25

    # Explicit contamination overrides
    model_override = IsolationForestModel(contamination=0.05, random_state=42)
    assert model_override.contamination == 0.05


def test_feature_importance_explanation() -> None:
    dataset = _generate_synthetic_dataset(15, 1)
    service = AnomalyDetectionService(random_state=42)
    results = service.fit_predict(dataset)

    outlier_result = next(r for r in results if r.institution_id == "inst-outlier-0")
    assert outlier_result.prediction == "anomalous"
    assert len(outlier_result.top_features) > 0

    # The outlier has huge values in seat_utilisation, intake_growth, backdated_admission_rate
    top_names = outlier_result.top_features
    assert any(
        f in top_names
        for f in (
            "seat_utilisation",
            "intake_growth",
            "backdated_admission_rate",
            "eligibility_violation_count",
            "zero_attrition_frequency",
        )
    )


def test_modular_model_substitution() -> None:
    class MockCustomAnomalyModel(BaseAnomalyModel):
        def __init__(self) -> None:
            self.fitted = False

        def fit(
            self,
            X: np.ndarray,
            feature_names: Sequence[str] | None = None,
        ) -> MockCustomAnomalyModel:
            self.fitted = True
            return self

        def predict(self, X: np.ndarray) -> np.ndarray:
            # Custom heuristic rule: if first feature > 1.0 -> -1, else 1
            return np.array([-1 if row[0] > 1.0 else 1 for row in X])

        def score_samples(self, X: np.ndarray) -> np.ndarray:
            return np.array([0.95 if row[0] > 1.0 else 0.15 for row in X])

    custom_model = MockCustomAnomalyModel()
    service = AnomalyDetectionService(model=custom_model)

    items = [
        {"institution_id": "inst-low", "seat_utilisation": 0.50},
        {"institution_id": "inst-high", "seat_utilisation": 1.50},
    ]
    results = service.fit_predict(items)

    assert custom_model.fitted is True
    assert results[0].prediction == "normal"
    assert results[0].score == 0.15
    assert results[1].prediction == "anomalous"
    assert results[1].score == 0.95


def test_rank_institutions_backward_compatibility() -> None:
    features = [
        InstitutionFeatures(
            institution_id=f"inst-normal-{i}",
            features={name: 0.1 for name in FEATURE_NAMES},
        )
        for i in range(10)
    ]
    features.append(
        InstitutionFeatures(
            institution_id="inst-outlier",
            features={
                "seat_utilisation": 2.5,
                "eligibility_violation_count": 50.0,
                "backdated_admission_rate": 0.9,
            },
        )
    )

    ranked = rank_institutions(features)
    assert len(ranked) == 11
    assert isinstance(ranked[0], AnomalyResult)
    # Most anomalous first
    assert ranked[0].score >= ranked[-1].score
    assert ranked[0].institution_id == "inst-outlier"


def test_anomaly_service_handles_edge_cases() -> None:
    service = AnomalyDetectionService(random_state=42)

    # Empty items
    assert service.predict([]) == []

    # Single item
    single_res = service.fit_predict([{"institution_id": "inst-solo", "seat_utilisation": 0.8}])
    assert len(single_res) == 1
    assert single_res[0].institution_id == "inst-solo"
    assert 0.0 <= single_res[0].score <= 1.0
