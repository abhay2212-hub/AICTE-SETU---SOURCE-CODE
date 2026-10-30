# Owner: Dev A
"""Comprehensive tests for evaluation metrics and ROC calculation."""

from __future__ import annotations

import pytest

from engine.evaluation.metrics import (
    BinaryClassificationMetrics,
    SignalRuleMetrics,
    compute_binary_metrics,
    compute_roc,
)


def test_confusion_matrix_and_derived_rates() -> None:
    # 2 TP, 1 FP, 1 FN, 2 TN
    y_true = [1, 1, 0, 1, 0, 0]
    y_pred = [1, 1, 1, 0, 0, 0]

    metrics = compute_binary_metrics(y_true, y_pred)

    assert metrics.tp == 2
    assert metrics.fp == 1
    assert metrics.fn == 1
    assert metrics.tn == 2

    # Precision: 2 / (2 + 1) = 2/3 ≈ 0.6667
    assert round(metrics.precision, 4) == 0.6667
    # Recall: 2 / (2 + 1) = 2/3 ≈ 0.6667
    assert round(metrics.recall, 4) == 0.6667
    # F1 Score: 2 * (2/3 * 2/3) / (4/3) = 2/3 ≈ 0.6667
    assert round(metrics.f1_score, 4) == 0.6667
    # Accuracy: (2 + 2) / 6 = 4/6 ≈ 0.6667
    assert round(metrics.accuracy, 4) == 0.6667
    # FPR: FP / (FP + TN) = 1 / (1 + 2) = 1/3 ≈ 0.3333
    assert round(metrics.false_positive_rate, 4) == 0.3333
    # FNR: FN / (TP + FN) = 1 / (2 + 1) = 1/3 ≈ 0.3333
    assert round(metrics.false_negative_rate, 4) == 0.3333
    # Specificity: TN / (TN + FP) = 2 / 3 ≈ 0.6667
    assert round(metrics.specificity, 4) == 0.6667


def test_metrics_zero_division_safety() -> None:
    # All negatives predicted negative: 0 TP, 0 FP, 0 FN, 3 TN
    y_true = [0, 0, 0]
    y_pred = [0, 0, 0]

    metrics = compute_binary_metrics(y_true, y_pred)
    assert metrics.tp == 0
    assert metrics.fp == 0
    assert metrics.fn == 0
    assert metrics.tn == 3
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.f1_score == 0.0
    assert metrics.accuracy == 1.0
    assert metrics.false_positive_rate == 0.0
    assert metrics.false_negative_rate == 0.0


def test_metrics_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="identical length"):
        compute_binary_metrics([1, 0], [1])


def test_roc_auc_perfect_classifier() -> None:
    y_true = [1, 1, 0, 0]
    y_scores = [0.9, 0.8, 0.2, 0.1]

    auc, curve = compute_roc(y_true, y_scores)
    assert auc == 1.0
    assert len(curve) > 0


def test_roc_auc_inverted_classifier() -> None:
    y_true = [1, 1, 0, 0]
    y_scores = [0.1, 0.2, 0.8, 0.9]

    auc, _ = compute_roc(y_true, y_scores)
    assert auc == 0.0


def test_signal_rule_metrics_serialization() -> None:
    sig_m = SignalRuleMetrics(
        signal_name="ELIGIBILITY_VIOLATION",
        total_generated=10,
        correctly_generated=8,
        false_signals=2,
        missed_signals=1,
        precision=0.80,
        recall=0.8889,
        f1_score=0.8421,
    )

    d = sig_m.to_dict()
    assert d["signal_name"] == "ELIGIBILITY_VIOLATION"
    assert d["correctly_generated"] == 8
    assert d["false_signals"] == 2
    assert d["precision"] == 0.80


def test_binary_metrics_to_dict() -> None:
    bm = BinaryClassificationMetrics(
        tp=5,
        fp=1,
        tn=10,
        fn=2,
        precision=0.8333,
        recall=0.7143,
        f1_score=0.7692,
        accuracy=0.8333,
        roc_auc=0.92,
    )
    d = bm.to_dict()
    assert d["tp"] == 5
    assert d["total_samples"] == 18
    assert d["roc_auc"] == 0.92
