# Owner: Dev A
"""Configurable weights and thresholds for Institution Integrity Scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.config import (
    ANOMALY_WEIGHT,
    BLIND_MATCH_WEIGHT,
    SCORE_THRESHOLD_HIGH,
    SCORE_THRESHOLD_LOW,
    SCORE_THRESHOLD_MEDIUM,
    SEVERITY_WEIGHT_ERROR,
    SEVERITY_WEIGHT_INFO,
    SEVERITY_WEIGHT_REVIEW,
    SEVERITY_WEIGHT_WARNING,
    SIGNAL_WEIGHT,
)


@dataclass
class ScoringWeights:
    """Configurable weights and thresholds for calculating institution integrity scores.

    All constants are loaded from engine configuration defaults and can be
    overridden per evaluation instance.
    """

    # Component weights
    signal_weight: float = field(default_factory=lambda: SIGNAL_WEIGHT)
    anomaly_weight: float = field(default_factory=lambda: ANOMALY_WEIGHT)
    blind_match_weight: float = field(default_factory=lambda: BLIND_MATCH_WEIGHT)

    # Signal severity deduction multipliers
    severity_weights: dict[str, float] = field(
        default_factory=lambda: {
            "error": SEVERITY_WEIGHT_ERROR,
            "review": SEVERITY_WEIGHT_REVIEW,
            "warning": SEVERITY_WEIGHT_WARNING,
            "info": SEVERITY_WEIGHT_INFO,
        }
    )

    # Blind match penalties
    blind_match_base_penalty: float = 20.0

    # Deduction caps per component to preserve balance
    max_signal_penalty: float = 100.0
    max_anomaly_penalty: float = 100.0
    max_blind_match_penalty: float = 100.0

    # Risk level classification thresholds
    threshold_low: float = field(default_factory=lambda: SCORE_THRESHOLD_LOW)
    threshold_medium: float = field(default_factory=lambda: SCORE_THRESHOLD_MEDIUM)
    threshold_high: float = field(default_factory=lambda: SCORE_THRESHOLD_HIGH)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ScoringWeights:
        """Create a ScoringWeights instance from a dictionary with fallback to defaults."""
        if not data:
            return cls()

        raw_sev = data.get("severity_weights", {})
        severity = {
            "error": float(data.get("severity_error", raw_sev.get("error", SEVERITY_WEIGHT_ERROR))),
            "review": float(
                data.get("severity_review", raw_sev.get("review", SEVERITY_WEIGHT_REVIEW))
            ),
            "warning": float(
                data.get("severity_warning", raw_sev.get("warning", SEVERITY_WEIGHT_WARNING))
            ),
            "info": float(data.get("severity_info", raw_sev.get("info", SEVERITY_WEIGHT_INFO))),
        }

        return cls(
            signal_weight=float(data.get("signal_weight", SIGNAL_WEIGHT)),
            anomaly_weight=float(data.get("anomaly_weight", ANOMALY_WEIGHT)),
            blind_match_weight=float(data.get("blind_match_weight", BLIND_MATCH_WEIGHT)),
            severity_weights=severity,
            blind_match_base_penalty=float(data.get("blind_match_base_penalty", 20.0)),
            max_signal_penalty=float(data.get("max_signal_penalty", 100.0)),
            max_anomaly_penalty=float(data.get("max_anomaly_penalty", 100.0)),
            max_blind_match_penalty=float(data.get("max_blind_match_penalty", 100.0)),
            threshold_low=float(data.get("threshold_low", SCORE_THRESHOLD_LOW)),
            threshold_medium=float(data.get("threshold_medium", SCORE_THRESHOLD_MEDIUM)),
            threshold_high=float(data.get("threshold_high", SCORE_THRESHOLD_HIGH)),
        )
