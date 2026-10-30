# Owner: Dev A
"""Evaluation of engine output against datagen ground truth."""

from __future__ import annotations

from typing import Any


def evaluate(
    predictions: list[dict[str, Any]], ground_truth: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return precision, recall and F1 per signal type.

    Keys both lists by (record_id, anomaly_type); per type counts true
    positives, false positives and false negatives; returns
    ``{type: {"precision": p, "recall": r, "f1": f1, "support": n}}``.
    """

    def _extract_key(item: dict[str, Any]) -> tuple[str, str]:
        rec = str(
            item.get("record_id") or item.get("student_id") or item.get("institution_id") or ""
        )
        anom = str(item.get("anomaly_type") or item.get("signal_name") or "")
        return rec, anom

    pred_keys = {_extract_key(p) for p in predictions}
    gt_keys = {_extract_key(g) for g in ground_truth}

    all_types = sorted({k[1] for k in pred_keys.union(gt_keys) if k[1]})

    results: dict[str, dict[str, Any]] = {}
    for anom_type in all_types:
        preds_for_type = {k for k in pred_keys if k[1] == anom_type}
        gts_for_type = {k for k in gt_keys if k[1] == anom_type}

        tp = len(preds_for_type.intersection(gts_for_type))
        fp = len(preds_for_type - gts_for_type)
        fn = len(gts_for_type - preds_for_type)

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        results[anom_type] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": len(gts_for_type),
        }

    return results
