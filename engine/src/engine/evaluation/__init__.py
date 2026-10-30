# Owner: Dev A
"""Evaluation Harness and Benchmarking Framework (Feature F24)."""

from __future__ import annotations

from engine.eval.harness import evaluate
from engine.evaluation.benchmark import BenchmarkRunner
from engine.evaluation.datasets import EvaluationDataset
from engine.evaluation.metrics import (
    BinaryClassificationMetrics,
    SignalRuleMetrics,
    compute_binary_metrics,
    compute_roc,
)
from engine.evaluation.report import EvaluationReport
from engine.evaluation.service import EvaluationService

__all__ = [
    "BenchmarkRunner",
    "BinaryClassificationMetrics",
    "EvaluationDataset",
    "EvaluationReport",
    "EvaluationService",
    "SignalRuleMetrics",
    "compute_binary_metrics",
    "compute_roc",
    "evaluate",
]
