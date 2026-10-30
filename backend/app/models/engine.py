# Owner: Dev A
"""Models for the Integrity Intelligence Engine contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.common import CaseStatus, IssueSeverity

RiskLevel = Literal["low", "medium", "high", "critical"]


class MatchCase(BaseModel):
    """Represents a potential duplicate between institutions."""

    case_id: str = Field(default_factory=lambda: str(uuid4()))
    institution_a: str
    institution_b: str
    student_a_id: str
    student_b_id: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    matched_fields: list[str] = Field(default_factory=list)
    status: CaseStatus = "open"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Signal(BaseModel):
    """An integrity signal raised against an institution."""

    signal_id: str = Field(default_factory=lambda: str(uuid4()))
    institution_id: str
    signal_name: str
    severity: IssueSeverity = "warning"
    score: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntegrityScore(BaseModel):
    """Institution integrity score with associated signals and risk assessment."""

    institution_id: str
    score: float = Field(ge=0.0, le=100.0)
    risk_level: RiskLevel = "low"
    components: dict[str, float] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    signals: list[Signal] = Field(default_factory=list)


class EngineInfo(BaseModel):
    """Engine metadata and runtime parameters."""

    name: str = "Integrity Intelligence Engine"
    version: str
    status: str = "active"
    match_threshold: float
    model_version: str


class EngineHealth(BaseModel):
    """Engine health status."""

    status: str = "ok"
    version: str
    engine_ok: bool = True


class BlindMatchStudentInput(BaseModel):
    """Input student record for blind match duplicate detection."""

    student_id: str
    institution_id: str
    student_name: str
    dob: str
    father_name: str = ""
    mother_name: str = ""
    apaar_id: str | None = None


class BlindMatchRequest(BaseModel):
    """Request payload for POST /engine/blind-match."""

    records: list[BlindMatchStudentInput]
    threshold: float | None = None


class SignalsRequest(BaseModel):
    """Request payload for POST /engine/signals."""

    institution_id: str | None = None
    admissions: list[dict[str, Any]] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
    seat_pools: list[dict[str, Any]] = Field(default_factory=list)
    historical_stats: list[dict[str, Any]] = Field(default_factory=list)
    rules_config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AnomalyPrediction(BaseModel):
    """Anomaly prediction result for one institution."""

    institution_id: str
    score: float = Field(ge=0.0, le=1.0)
    prediction: str = "normal"
    top_features: list[str] = Field(default_factory=list)
    feature_vector: dict[str, float] = Field(default_factory=dict)


class AnomalyRequest(BaseModel):
    """Request payload for POST /engine/anomaly."""

    institutions: list[dict[str, Any]] = Field(default_factory=list)
    features: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class IntegrityScoreRequest(BaseModel):
    """Request payload for POST /engine/integrity-score."""

    institution_id: str = "unknown"
    signals: list[Signal] = Field(default_factory=list)
    anomaly_score: float | None = None
    blind_matches: list[MatchCase] = Field(default_factory=list)
    weights: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}
