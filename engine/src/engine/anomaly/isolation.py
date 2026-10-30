# Owner: Dev A
"""Unsupervised ranking of institutions by how anomalous their admission profile looks."""

from __future__ import annotations

from engine.anomaly.service import AnomalyDetectionService
from engine.types import AnomalyResult, InstitutionFeatures


def rank_institutions(features: list[InstitutionFeatures]) -> list[AnomalyResult]:
    """Rank institutions with an Isolation Forest, most anomalous first.

    Builds a matrix from each institution's feature vector in deterministic
    feature order, fits the Isolation Forest model, maps samples to a 0-1
    anomaly score, explains results with z-score deviation, and returns
    results sorted with the highest anomaly score first.
    """
    if not features:
        return []

    service = AnomalyDetectionService()
    results = service.fit_predict(features)
    # Sort most anomalous first
    results.sort(key=lambda r: r.score, reverse=True)
    return results
