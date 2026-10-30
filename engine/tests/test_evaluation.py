# Owner: Dev A
"""Comprehensive tests for EvaluationService and EvaluationReport."""

from __future__ import annotations

import json
from pathlib import Path

from engine.eval.harness import evaluate as legacy_evaluate
from engine.evaluation.datasets import EvaluationDataset
from engine.evaluation.report import EvaluationReport
from engine.evaluation.service import EvaluationService


def test_dataset_json_serialization_and_deserialization(tmp_path: Path) -> None:
    ds = EvaluationDataset.create_synthetic_benchmark_dataset()
    json_str = ds.to_json()
    assert isinstance(json_str, str)

    # Save to file and reload
    save_file = tmp_path / "test_dataset.json"
    ds.save(save_file)
    assert save_file.exists()

    loaded = EvaluationDataset.from_file(save_file)
    assert loaded.dataset_id == ds.dataset_id
    assert len(loaded.blind_match_records) == len(ds.blind_match_records)
    assert len(loaded.blind_match_ground_truth) == len(ds.blind_match_ground_truth)
    assert len(loaded.anomaly_institutions) == len(ds.anomaly_institutions)


def test_evaluate_blind_match_multi_threshold() -> None:
    service = EvaluationService()
    dataset = EvaluationDataset.create_synthetic_benchmark_dataset()

    res = service.evaluate_blind_match(dataset, threshold=0.85, threshold_sweep=[0.75, 0.85, 0.95])
    assert "metrics" in res
    assert "threshold_sweep" in res

    metrics = res["metrics"]
    assert metrics["precision"] > 0.0
    assert metrics["recall"] > 0.0
    assert metrics["f1_score"] > 0.0
    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert "false_positive_rate" in metrics
    assert "false_negative_rate" in metrics

    sweep = res["threshold_sweep"]
    assert len(sweep) == 3
    # Check that each threshold step has recorded metrics
    for step in sweep:
        assert "threshold" in step
        assert "f1_score" in step


def test_evaluate_signals_with_per_signal_statistics() -> None:
    service = EvaluationService()
    dataset = EvaluationDataset.create_synthetic_benchmark_dataset()

    res = service.evaluate_signals(dataset)
    assert res["signals_generated"] > 0
    assert res["correctly_generated"] > 0
    assert res["precision"] > 0.0
    assert res["recall"] > 0.0
    assert res["f1_score"] > 0.0

    per_signal = res["per_signal_statistics"]
    assert isinstance(per_signal, dict)
    assert "ELIGIBILITY_VIOLATION" in per_signal
    assert "BACKDATED_ADMISSIONS" in per_signal

    elig_stats = per_signal["ELIGIBILITY_VIOLATION"]
    assert elig_stats["correctly_generated"] >= 1
    assert elig_stats["precision"] > 0.0


def test_evaluate_anomaly_detection_with_roc() -> None:
    service = EvaluationService()
    dataset = EvaluationDataset.create_synthetic_benchmark_dataset()

    res = service.evaluate_anomaly_detection(dataset)
    assert "metrics" in res
    metrics = res["metrics"]
    assert metrics["precision"] > 0.0
    assert metrics["recall"] > 0.0
    assert metrics["f1_score"] > 0.0
    assert metrics["accuracy"] > 0.80
    assert metrics["roc_auc"] is not None
    assert metrics["roc_auc"] >= 0.70
    assert len(metrics["roc_curve"]) > 0


def test_evaluate_integrity_score_consistency() -> None:
    service = EvaluationService()
    dataset = EvaluationDataset.create_synthetic_benchmark_dataset()

    res = service.evaluate_integrity_score(dataset)
    assert res["deterministic_outputs_verified"] is True
    assert res["risk_level_mapping_verified"] is True
    assert res["configurable_weights_verified"] is True
    assert res["score_stability_verified"] is True
    assert res["status"] == "passed"


def test_run_full_evaluation_and_report_generation(tmp_path: Path) -> None:
    service = EvaluationService()
    dataset = EvaluationDataset.create_synthetic_benchmark_dataset()

    report = service.run_full_evaluation(dataset, include_benchmarks=True)
    assert isinstance(report, EvaluationReport)

    r_dict = report.to_dict()
    assert "blind_match" in r_dict
    assert "signals" in r_dict
    assert "anomaly_detection" in r_dict
    assert "integrity_score" in r_dict
    assert "benchmark" in r_dict
    assert "summary" in r_dict
    assert "generated_at" in r_dict

    # Determinism verification: evaluate twice
    report2 = service.run_full_evaluation(dataset, include_benchmarks=False)
    assert report.summary["blind_match_f1"] == report2.summary["blind_match_f1"]
    assert report.summary["anomaly_detection_f1"] == report2.summary["anomaly_detection_f1"]

    # File saving
    report_file = tmp_path / "evaluation.json"
    report.save(report_file)
    assert report_file.exists()
    loaded = json.loads(report_file.read_text(encoding="utf-8"))
    assert loaded["summary"]["status"] == "completed"


def test_legacy_eval_harness_evaluate() -> None:
    preds = [
        {"record_id": "r1", "anomaly_type": "intake_overrun"},
        {"record_id": "r2", "anomaly_type": "dup_cross_institution"},
        {"record_id": "r3", "anomaly_type": "intake_overrun"},
    ]
    gt = [
        {"record_id": "r1", "anomaly_type": "intake_overrun"},
        {"record_id": "r2", "anomaly_type": "dup_cross_institution"},
        {"record_id": "r4", "anomaly_type": "intake_overrun"},
    ]

    res = legacy_evaluate(preds, gt)
    assert "intake_overrun" in res
    assert "dup_cross_institution" in res

    # dup_cross_institution: 1 TP, 0 FP, 0 FN -> P=1, R=1, F1=1
    assert res["dup_cross_institution"]["precision"] == 1.0
    assert res["dup_cross_institution"]["recall"] == 1.0
    assert res["dup_cross_institution"]["support"] == 1

    # intake_overrun: 1 TP (r1), 1 FP (r3), 1 FN (r4) -> P=0.5, R=0.5, F1=0.5
    assert res["intake_overrun"]["precision"] == 0.5
    assert res["intake_overrun"]["recall"] == 0.5
    assert res["intake_overrun"]["f1"] == 0.5
    assert res["intake_overrun"]["support"] == 2
