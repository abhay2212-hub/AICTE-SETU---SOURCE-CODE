# Owner: Dev A
"""Structured evaluation report generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class EvaluationReport:
    """Complete evaluation report covering Blind Match, Signals, ML Anomaly Detection,

    Integrity Scoring, and Benchmarking performance.
    """

    blind_match: dict[str, Any] = field(default_factory=dict)
    signals: dict[str, Any] = field(default_factory=dict)
    anomaly_detection: dict[str, Any] = field(default_factory=dict)
    integrity_score: dict[str, Any] = field(default_factory=dict)
    benchmark: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary format matching the platform contract."""
        return {
            "blind_match": self.blind_match,
            "signals": self.signals,
            "anomaly_detection": self.anomaly_detection,
            "integrity_score": self.integrity_score,
            "benchmark": self.benchmark,
            "summary": self.summary,
            "generated_at": self.generated_at,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize report to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, file_path: str | Path = "evaluation.json") -> None:
        """Save report to a local file (e.g. evaluation.json)."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
