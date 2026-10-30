# Owner: Dev A
"""Shared dataclasses passed between engine modules and the backend."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

Severity = Literal["error", "warning", "review", "info"]


@dataclass(frozen=True)
class EncodedRecord:
    """A student identity reduced to a Bloom-filter encoding. No raw identity fields."""

    record_id: str
    institution_id: str
    bloom: bytes
    birth_year_hash: str
    apaar_id: str | None = None


@dataclass(frozen=True)
class MatchCandidate:
    """A pair of encoded records that probably refer to the same person."""

    record_a: str
    record_b: str
    dice: float
    same_institution: bool = False


@dataclass
class MatchCase:
    """Represents a potential duplicate between institutions."""

    institution_a: str
    institution_b: str
    student_a_id: str
    student_b_id: str
    similarity_score: float
    confidence: float
    case_id: str = field(default_factory=lambda: str(uuid4()))
    matched_fields: list[str] = field(default_factory=list)
    status: str = "open"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Signal:
    """A rule-based integrity signal raised against an institution."""

    code: str = ""
    institution_id: str = ""
    severity: Severity = "warning"
    evidence: dict[str, Any] = field(default_factory=dict)
    signal_id: str = field(default_factory=lambda: str(uuid4()))
    signal_name: str = ""
    score: float = 0.0
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.signal_name and self.code:
            self.signal_name = self.code
        elif not self.code and self.signal_name:
            self.code = self.signal_name


@dataclass
class InstitutionFeatures:
    """Per-institution feature vector used for anomaly ranking."""

    institution_id: str
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class AnomalyResult:
    """Isolation Forest output for one institution. Higher score means more anomalous."""

    institution_id: str
    score: float
    prediction: str = "normal"
    top_features: list[str] = field(default_factory=list)
    feature_vector: dict[str, float] = field(default_factory=dict)


@dataclass
class IntegrityScore:
    """Integrity Score from 0 (worst) to 100 (clean), with the deduction for each component."""

    institution_id: str
    score: float
    components: dict[str, float] = field(default_factory=dict)
    risk_level: str = "low"
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    signals: list[Signal] = field(default_factory=list)
