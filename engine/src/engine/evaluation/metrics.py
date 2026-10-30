# Owner: Dev A
"""Evaluation metrics calculation for classification, signals, and ROC analysis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BinaryClassificationMetrics:
    """Confusion matrix and classification performance metrics."""

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    accuracy: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    specificity: float = 0.0
    roc_auc: float | None = None
    roc_curve: list[dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics to dictionary."""
        d: dict[str, Any] = {
            "tp": self.tp,
            "fp": self.fp,
            "tn": self.tn,
            "fn": self.fn,
            "total_samples": self.tp + self.fp + self.tn + self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "accuracy": round(self.accuracy, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "false_negative_rate": round(self.false_negative_rate, 4),
            "specificity": round(self.specificity, 4),
        }
        if self.roc_auc is not None:
            d["roc_auc"] = round(self.roc_auc, 4)
        if self.roc_curve:
            d["roc_curve"] = self.roc_curve
        return d


@dataclass
class SignalRuleMetrics:
    """Per-signal rule detection statistics."""

    signal_name: str
    total_generated: int = 0
    correctly_generated: int = 0  # True positives
    false_signals: int = 0  # False positives
    missed_signals: int = 0  # False negatives
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "total_generated": self.total_generated,
            "correctly_generated": self.correctly_generated,
            "false_signals": self.false_signals,
            "missed_signals": self.missed_signals,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
        }


def compute_binary_metrics(
    y_true: Sequence[bool | int],
    y_pred: Sequence[bool | int],
    y_scores: Sequence[float] | None = None,
) -> BinaryClassificationMetrics:
    """Calculate confusion matrix and derived rates for binary predictions."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have identical length.")

    tp = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if bool(yt) and bool(yp))
    fp = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if not bool(yt) and bool(yp))
    tn = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if not bool(yt) and not bool(yp))
    fn = sum(1 for yt, yp in zip(y_true, y_pred, strict=True) if bool(yt) and not bool(yp))

    total = tp + fp + tn + fn
    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    accuracy = ((tp + tn) / total) if total > 0 else 0.0
    fpr = (fp / (fp + tn)) if (fp + tn) > 0 else 0.0
    fnr = (fn / (tp + fn)) if (tp + fn) > 0 else 0.0
    specificity = (tn / (tn + fp)) if (tn + fp) > 0 else 0.0

    roc_auc = None
    roc_curve: list[dict[str, float]] = []

    if y_scores is not None and len(y_scores) == len(y_true):
        roc_auc, roc_curve = compute_roc(y_true, y_scores)

    return BinaryClassificationMetrics(
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        accuracy=accuracy,
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        specificity=specificity,
        roc_auc=roc_auc,
        roc_curve=roc_curve,
    )


def compute_roc(
    y_true: Sequence[bool | int],
    y_scores: Sequence[float],
) -> tuple[float, list[dict[str, float]]]:
    """Compute ROC points and ROC-AUC via trapezoidal integration."""
    bool_true = [bool(yt) for yt in y_true]
    n_pos = sum(1 for yt in bool_true if yt)
    n_neg = len(bool_true) - n_pos

    if n_pos == 0 or n_neg == 0:
        return 0.5, [{"threshold": 0.0, "fpr": 0.0, "tpr": 0.0}]

    # Unique thresholds sorted descending
    sorted_pairs = sorted(zip(y_scores, bool_true, strict=True), key=lambda x: x[0], reverse=True)
    thresholds = sorted({score for score, _ in sorted_pairs}, reverse=True)

    points: list[dict[str, float]] = [{"threshold": float("inf"), "fpr": 0.0, "tpr": 0.0}]
    auc = 0.0
    prev_fpr = 0.0
    prev_tpr = 0.0

    for thresh in thresholds:
        tp_count = sum(1 for s, yt in sorted_pairs if s >= thresh and yt)
        fp_count = sum(1 for s, yt in sorted_pairs if s >= thresh and not yt)

        tpr = tp_count / n_pos
        fpr = fp_count / n_neg

        # Trapezoidal area increment
        auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2.0
        prev_fpr = fpr
        prev_tpr = tpr

        points.append(
            {
                "threshold": round(float(thresh), 4),
                "fpr": round(fpr, 4),
                "tpr": round(tpr, 4),
            }
        )

    # Ensure ending at (1.0, 1.0)
    if prev_fpr < 1.0:
        auc += (1.0 - prev_fpr) * (1.0 + prev_tpr) / 2.0
        points.append({"threshold": 0.0, "fpr": 1.0, "tpr": 1.0})

    return round(float(auc), 4), points
