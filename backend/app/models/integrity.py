# Owner: Dev B (contract consumed by Dev A's integrity router)
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.common import IssueSeverity


class IntegrityRanking(BaseModel):
    rank: int
    institution_id: str
    institution_name: str
    aicte_code: str
    integrity_score: float
    anomaly_score: float
    top_signals: list[str]


class SignalOut(BaseModel):
    code: str
    severity: IssueSeverity
    evidence: dict[str, Any]


class AnomalyFeature(BaseModel):
    name: str
    value: float
    peer_median: float


class AnomalyExplanation(BaseModel):
    score: float
    top_features: list[AnomalyFeature]


class IntegrityDetail(BaseModel):
    institution_id: str
    integrity_score: float
    components: dict[str, float]
    signals: list[SignalOut]
    anomaly: AnomalyExplanation
