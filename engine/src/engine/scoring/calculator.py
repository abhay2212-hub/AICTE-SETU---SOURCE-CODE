# Owner: Dev A
"""Deterministic Integrity Score calculator combining signals, anomaly, and blind match."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from engine.scoring.weights import ScoringWeights
from engine.types import AnomalyResult, IntegrityScore, MatchCase, Signal


def map_risk_level(
    score: float,
    weights: ScoringWeights | None = None,
    title_case: bool = False,
) -> str:
    """Map a 0-100 score to a risk level based on configurable thresholds.

    Thresholds:
      - score >= threshold_low (default 80): Low
      - score >= threshold_medium (default 60): Medium
      - score >= threshold_high (default 40): High
      - score < threshold_high: Critical
    """
    w = weights if weights is not None else ScoringWeights()

    if score >= w.threshold_low:
        level = "low"
    elif score >= w.threshold_medium:
        level = "medium"
    elif score >= w.threshold_high:
        level = "high"
    else:
        level = "critical"

    return level.capitalize() if title_case else level


class IntegrityScoreCalculator:
    """Calculates deterministic institution integrity scores (0-100) from

    rule-based signals, ML anomaly detection, and blind match duplicates.
    """

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights if weights is not None else ScoringWeights()

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
        w = weights if weights is not None else self.weights

        # 1. Normalize signals and calculate signal penalty
        normalized_signals: list[Signal] = []
        raw_signal_penalty = 0.0

        if signals:
            for s in signals:
                if isinstance(s, Signal):
                    sig = s
                elif isinstance(s, dict):
                    sig = Signal(
                        signal_id=str(s.get("signal_id", "")),
                        institution_id=str(s.get("institution_id") or institution_id),
                        signal_name=str(s.get("signal_name") or s.get("code", "")),
                        severity=s.get("severity", "warning"),
                        score=float(s.get("score", 0.0)),
                        evidence=s.get("evidence", {}),
                        description=str(s.get("description", "")),
                    )
                else:
                    continue

                normalized_signals.append(sig)
                sev_key = str(sig.severity).lower()
                deduction = w.severity_weights.get(sev_key, w.severity_weights.get("warning", 8.0))
                raw_signal_penalty += deduction

        capped_signal_penalty = min(w.max_signal_penalty, raw_signal_penalty)
        signal_deduction = w.signal_weight * capped_signal_penalty

        # 2. Anomaly penalty
        if isinstance(anomaly, AnomalyResult):
            anomaly_score = float(anomaly.score)
        elif isinstance(anomaly, (int, float)):
            anomaly_score = float(anomaly)
        else:
            anomaly_score = 0.0

        clamped_anomaly_score = max(0.0, min(1.0, anomaly_score))
        raw_anomaly_penalty = clamped_anomaly_score * w.max_anomaly_penalty
        capped_anomaly_penalty = min(w.max_anomaly_penalty, raw_anomaly_penalty)
        anomaly_deduction = w.anomaly_weight * capped_anomaly_penalty

        # 3. Blind match duplicate penalty
        raw_bm_penalty = 0.0
        if blind_matches:
            for m in blind_matches:
                if isinstance(m, MatchCase):
                    conf = float(m.confidence or m.similarity_score or 1.0)
                elif isinstance(m, dict):
                    conf = float(m.get("confidence") or m.get("similarity_score") or 1.0)
                else:
                    conf = 1.0
                raw_bm_penalty += w.blind_match_base_penalty * max(0.0, min(1.0, conf))

        capped_bm_penalty = min(w.max_blind_match_penalty, raw_bm_penalty)
        blind_match_deduction = w.blind_match_weight * capped_bm_penalty

        # 4. Total deductions and final clamped score
        total_deduction = signal_deduction + anomaly_deduction + blind_match_deduction
        final_score = round(max(0.0, min(100.0, 100.0 - total_deduction)), 2)

        # 5. Risk level mapping
        risk_level = map_risk_level(final_score, weights=w, title_case=title_case_risk)

        components = {
            "signals_deduction": round(signal_deduction, 2),
            "anomaly_deduction": round(anomaly_deduction, 2),
            "blind_match_deduction": round(blind_match_deduction, 2),
            "total_deduction": round(total_deduction, 2),
        }

        return IntegrityScore(
            institution_id=institution_id,
            score=final_score,
            components=components,
            risk_level=risk_level,
            generated_at=datetime.now(UTC),
            signals=normalized_signals,
        )
