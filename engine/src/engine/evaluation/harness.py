# Owner: Dev A
"""Evaluation harness module alias for engine.eval.harness and engine.evaluation.service."""

from __future__ import annotations

from engine.eval.harness import evaluate
from engine.evaluation.service import EvaluationService

__all__ = ["EvaluationService", "evaluate"]
