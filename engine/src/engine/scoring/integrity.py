# Owner: Dev A
"""Integrity Score: one 0-100 number per institution."""

from __future__ import annotations

from engine.scoring.service import IntegrityScoringService
from engine.types import AnomalyResult, IntegrityScore, Signal


def integrity_score(signals: list[Signal], anomaly: AnomalyResult | None) -> IntegrityScore:
    """Combine signals and the anomaly result into a score from 0 (worst) to 100 (clean).

    Starts at 100, subtracts weighted penalties per signal by severity,
    subtracts penalty proportional to anomaly score, clamps to [0, 100],
    and records deductions in components.
    """
    institution_id = "unknown_inst"
    if signals and signals[0].institution_id:
        institution_id = signals[0].institution_id
    elif anomaly and anomaly.institution_id:
        institution_id = anomaly.institution_id

    service = IntegrityScoringService()
    return service.calculate(
        institution_id=institution_id,
        signals=signals,
        anomaly=anomaly,
    )
