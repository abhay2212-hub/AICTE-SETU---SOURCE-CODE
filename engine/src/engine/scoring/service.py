# Owner: Dev A
"""Service orchestrating in-memory Institution Integrity Scoring."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from engine.scoring.calculator import IntegrityScoreCalculator
from engine.scoring.weights import ScoringWeights
from engine.types import AnomalyResult, IntegrityScore, MatchCase, Signal


class IntegrityScoringService:
    """Service orchestrating institution integrity score calculation.

    Integrates signals, ML anomaly scores, and blind match linkage results
    into a unified 0-100 score and risk classification.
    """

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights if weights is not None else ScoringWeights()
        self.calculator = IntegrityScoreCalculator(weights=self.weights)

    def calculate(
        self,
        institution_id: str,
        signals: Sequence[Signal | dict[str, Any]] | None = None,
        anomaly: AnomalyResult | float | None = None,
        blind_matches: Sequence[MatchCase | dict[str, Any]] | None = None,
        weights: ScoringWeights | None = None,
        title_case_risk: bool = False,
    ) -> IntegrityScore:
        """Calculate the integrity score for a single institution."""
        active_weights = weights if weights is not None else self.weights
        return self.calculator.calculate(
            institution_id=institution_id,
            signals=signals,
            anomaly=anomaly,
            blind_matches=blind_matches,
            weights=active_weights,
            title_case_risk=title_case_risk,
        )

    def calculate_from_data(
        self,
        data: dict[str, Any],
        weights: ScoringWeights | None = None,
        title_case_risk: bool = False,
    ) -> IntegrityScore:
        """Calculate the integrity score from an institution data dictionary.

        Supports pre-computed signals/anomalies/matches or raw admissions.
        """
        institution_id = str(data.get("institution_id") or "inst-unknown")

        # Custom weights if passed in data
        w = weights
        if w is None and "weights" in data and isinstance(data["weights"], dict):
            w = ScoringWeights.from_dict(data["weights"])

        # Signals
        signals: list[Any] = data.get("signals") or []
        if not signals and ("admissions" in data or "records" in data):
            try:
                from engine.signals import execute_signals

                signals = execute_signals(data)
            except Exception:
                signals = []

        # Anomaly score / AnomalyResult
        anomaly = data.get("anomaly") or data.get("anomaly_score")
        if anomaly is None and "features" in data:
            try:
                from engine.anomaly.service import AnomalyDetectionService

                anomaly_service = AnomalyDetectionService()
                preds = anomaly_service.predict([data])
                if preds:
                    anomaly = preds[0]
            except Exception:
                anomaly = 0.0

        # Blind match results
        blind_matches: list[Any] = data.get("blind_matches") or data.get("matches") or []

        return self.calculate(
            institution_id=institution_id,
            signals=signals,
            anomaly=anomaly,
            blind_matches=blind_matches,
            weights=w,
            title_case_risk=title_case_risk,
        )

    def calculate_batch(
        self,
        batch: Sequence[dict[str, Any]],
        weights: ScoringWeights | None = None,
        title_case_risk: bool = False,
    ) -> list[IntegrityScore]:
        """Calculate integrity scores for a batch of institutions."""
        return [
            self.calculate_from_data(item, weights=weights, title_case_risk=title_case_risk)
            for item in batch
        ]
