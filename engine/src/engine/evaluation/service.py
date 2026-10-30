# Owner: Dev A
"""Evaluation service orchestrating multi-domain verification and reporting."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from engine.anomaly.service import AnomalyDetectionService
from engine.blind_match.models import StudentRecord
from engine.blind_match.service import BlindMatchService
from engine.evaluation.benchmark import BenchmarkRunner
from engine.evaluation.datasets import EvaluationDataset
from engine.evaluation.metrics import (
    BinaryClassificationMetrics,
    SignalRuleMetrics,
    compute_binary_metrics,
)
from engine.evaluation.report import EvaluationReport
from engine.scoring.calculator import IntegrityScoreCalculator, map_risk_level
from engine.scoring.service import IntegrityScoringService
from engine.scoring.weights import ScoringWeights
from engine.signals import execute_signals


class EvaluationService:
    """Service evaluating Blind Match, Integrity Signals, ML Anomaly Detection,

    Integrity Scoring, and Engine Benchmarks.
    """

    def __init__(self, secret: str = "eval-secret-key-32b-length") -> None:
        self.secret = secret
        self.benchmark_runner = BenchmarkRunner(runs=1)

    def evaluate_blind_match(
        self,
        dataset: EvaluationDataset,
        threshold: float = 0.85,
        threshold_sweep: list[float] | None = None,
    ) -> dict[str, Any]:
        """Evaluate Blind Match linking performance against ground-truth pairs."""
        records = dataset.blind_match_records
        gt_pairs = dataset.blind_match_ground_truth

        if not records or not gt_pairs:
            empty_metrics = BinaryClassificationMetrics().to_dict()
            return {
                "default_threshold": threshold,
                "metrics": empty_metrics,
                "threshold_sweep": [],
                "total_ground_truth_pairs": len(gt_pairs),
            }

        students = [
            StudentRecord(
                student_id=str(r.get("student_id", f"s-{i}")),
                institution_id=str(r.get("institution_id", f"inst-{i}")),
                student_name=str(r.get("student_name", "Student")),
                dob=str(r.get("dob", "2004-01-01")),
                father_name=str(r.get("father_name", "")),
                mother_name=str(r.get("mother_name", "")),
                apaar_id=r.get("apaar_id"),
            )
            for i, r in enumerate(records)
        ]

        def _evaluate_at_threshold(t: float) -> BinaryClassificationMetrics:
            service = BlindMatchService(secret=self.secret, threshold=t)
            matches = service.run_blind_match(students, threshold=t)

            detected_pairs: set[frozenset[str]] = {
                frozenset([m.student_a_id, m.student_b_id]) for m in matches
            }

            y_true: list[bool] = []
            y_pred: list[bool] = []
            y_scores: list[float] = []

            for gt in gt_pairs:
                id_a = str(gt.get("student_a_id") or gt.get("record_a", ""))
                id_b = str(gt.get("student_b_id") or gt.get("record_b", ""))
                pair_key = frozenset([id_a, id_b])

                is_dup = bool(gt.get("is_duplicate", False))
                pred_dup = pair_key in detected_pairs

                # Similarity score if matched
                match_obj = next(
                    (m for m in matches if frozenset([m.student_a_id, m.student_b_id]) == pair_key),
                    None,
                )
                score = match_obj.similarity_score if match_obj else 0.0

                y_true.append(is_dup)
                y_pred.append(pred_dup)
                y_scores.append(score)

            return compute_binary_metrics(y_true, y_pred, y_scores)

        primary_metrics = _evaluate_at_threshold(threshold)

        # Multi-threshold sweep
        sweeps: list[dict[str, Any]] = []
        sweep_thresholds = (
            threshold_sweep if threshold_sweep is not None else [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
        )
        for t in sweep_thresholds:
            m = _evaluate_at_threshold(t)
            sweeps.append(
                {
                    "threshold": t,
                    "precision": round(m.precision, 4),
                    "recall": round(m.recall, 4),
                    "f1_score": round(m.f1_score, 4),
                    "accuracy": round(m.accuracy, 4),
                    "tp": m.tp,
                    "fp": m.fp,
                    "fn": m.fn,
                    "tn": m.tn,
                }
            )

        return {
            "default_threshold": threshold,
            "metrics": primary_metrics.to_dict(),
            "threshold_sweep": sweeps,
            "total_ground_truth_pairs": len(gt_pairs),
        }

    def evaluate_signals(self, dataset: EvaluationDataset) -> dict[str, Any]:
        """Evaluate rule-based integrity signals against expected ground-truth signals."""
        signals_payload = dataset.signals_data
        gt_signals = dataset.signals_ground_truth

        generated = execute_signals(signals_payload)

        # Helper to generate matching keys for signals
        def _get_key(item: Any) -> tuple[str, str]:
            if isinstance(item, dict):
                inst = str(item.get("institution_id", ""))
                name = str(item.get("signal_name", "")).upper()
                return inst, name
            inst = str(getattr(item, "institution_id", ""))
            name = str(getattr(item, "signal_name", "")).upper()
            return inst, name

        def _get_student_key(item: Any) -> tuple[str, str, str]:
            inst, name = _get_key(item)
            stu = ""
            if isinstance(item, dict):
                ev = item.get("evidence", {})
                stu = str(item.get("student_id", "") or ev.get("student_id", ""))
            else:
                stu = str(getattr(item, "evidence", {}).get("student_id", ""))
            return inst, name, stu

        # Build lookup sets
        gen_keys = {_get_key(s) for s in generated}
        gen_stu_keys = {_get_student_key(s) for s in generated}

        # Track true positives, false negatives
        matched_gt_indices: set[int] = set()
        matched_gen_indices: set[int] = set()

        for gt_idx, gt in enumerate(gt_signals):
            k = _get_key(gt)
            sk = _get_student_key(gt)
            # Match by student-specific key if provided, else institution+rule key
            if sk[2] and sk in gen_stu_keys:
                matched_gt_indices.add(gt_idx)
                for gen_idx, gen in enumerate(generated):
                    if _get_student_key(gen) == sk:
                        matched_gen_indices.add(gen_idx)
            elif k in gen_keys:
                matched_gt_indices.add(gt_idx)
                for gen_idx, gen in enumerate(generated):
                    if _get_key(gen) == k:
                        matched_gen_indices.add(gen_idx)

        tp = len(matched_gt_indices)
        fn = len(gt_signals) - tp
        fp = len(generated) - len(matched_gen_indices)

        precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        # Per-signal breakdown
        all_rule_names = sorted(
            {_get_key(s)[1] for s in generated}.union({_get_key(gt)[1] for gt in gt_signals})
        )

        per_signal_stats: dict[str, dict[str, Any]] = {}
        for r_name in all_rule_names:
            gen_r = [s for s in generated if _get_key(s)[1] == r_name]
            gt_r = [gt for gt in gt_signals if _get_key(gt)[1] == r_name]

            # Matching for this rule
            r_tp = sum(1 for gt in gt_r if _get_key(gt) in {_get_key(s) for s in gen_r})
            r_fn = len(gt_r) - r_tp
            r_fp = len(gen_r) - r_tp

            r_p = (r_tp / (r_tp + r_fp)) if (r_tp + r_fp) > 0 else 0.0
            r_r = (r_tp / (r_tp + r_fn)) if (r_tp + r_fn) > 0 else 0.0
            r_f1 = (2 * r_p * r_r / (r_p + r_r)) if (r_p + r_r) > 0 else 0.0

            stat = SignalRuleMetrics(
                signal_name=r_name,
                total_generated=len(gen_r),
                correctly_generated=r_tp,
                false_signals=r_fp,
                missed_signals=r_fn,
                precision=r_p,
                recall=r_r,
                f1_score=r_f1,
            )
            per_signal_stats[r_name] = stat.to_dict()

        return {
            "signals_generated": len(generated),
            "correctly_generated": tp,
            "false_signals": fp,
            "missed_signals": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "per_signal_statistics": per_signal_stats,
        }

    def evaluate_anomaly_detection(self, dataset: EvaluationDataset) -> dict[str, Any]:
        """Evaluate Isolation Forest anomaly classification against ground truth labels."""
        institutions = dataset.anomaly_institutions
        gt_map = dataset.anomaly_ground_truth

        if not institutions:
            return {"metrics": BinaryClassificationMetrics().to_dict()}

        service = AnomalyDetectionService(random_state=42)
        results = service.fit_predict(institutions)

        y_true: list[bool] = []
        y_pred: list[bool] = []
        y_scores: list[float] = []
        detailed_institutions: list[dict[str, Any]] = []

        for r in results:
            expected = bool(gt_map.get(r.institution_id, False))
            predicted = r.prediction == "anomalous"
            score = float(r.score)

            y_true.append(expected)
            y_pred.append(predicted)
            y_scores.append(score)

            detailed_institutions.append(
                {
                    "institution_id": r.institution_id,
                    "expected": expected,
                    "predicted": predicted,
                    "score": score,
                    "top_features": r.top_features,
                }
            )

        metrics = compute_binary_metrics(y_true, y_pred, y_scores)

        return {
            "metrics": metrics.to_dict(),
            "institutions_evaluated": len(institutions),
            "detailed_results": detailed_institutions,
        }

    def evaluate_integrity_score(self, dataset: EvaluationDataset) -> dict[str, Any]:
        """Verify score consistency, determinism, stability, and risk level mapping."""
        insts = dataset.integrity_institutions or [
            {"institution_id": "eval-clean", "anomaly_score": 0.05, "signals": []},
            {
                "institution_id": "eval-critical",
                "anomaly_score": 0.90,
                "signals": [{"signal_name": "BACKDATED_ADMISSIONS", "severity": "error"}],
            },
        ]

        scoring_service = IntegrityScoringService()

        # 1. Deterministic verification: Run identical input twice
        first_pass = scoring_service.calculate_batch(insts)
        second_pass = scoring_service.calculate_batch(insts)

        is_deterministic = all(
            p1.score == p2.score and p1.risk_level == p2.risk_level
            for p1, p2 in zip(first_pass, second_pass, strict=True)
        )

        # 2. Risk level mapping verification across standard thresholds
        calc = IntegrityScoreCalculator()
        risk_checks = {
            "low": map_risk_level(85.0) == "low",
            "medium": map_risk_level(70.0) == "medium",
            "high": map_risk_level(50.0) == "high",
            "critical": map_risk_level(30.0) == "critical",
        }
        risk_mapping_verified = all(risk_checks.values())

        # 3. Configurable weight behavior verification
        w_default = ScoringWeights(signal_weight=0.4, anomaly_weight=0.35)
        w_heavy_anomaly = ScoringWeights(signal_weight=0.1, anomaly_weight=0.8)

        score_default = calc.calculate("inst-w", anomaly=0.5, weights=w_default)
        score_heavy = calc.calculate("inst-w", anomaly=0.5, weights=w_heavy_anomaly)

        weights_behavior_verified = (
            score_heavy.components["anomaly_deduction"]
            > score_default.components["anomaly_deduction"]
        )

        # 4. Score stability: clean institution should score higher than severely flagged
        score_stability_verified = True
        if len(first_pass) >= 2:
            score_stability_verified = first_pass[0].score >= first_pass[-1].score

        return {
            "deterministic_outputs_verified": is_deterministic,
            "risk_level_mapping_verified": risk_mapping_verified,
            "configurable_weights_verified": weights_behavior_verified,
            "score_stability_verified": score_stability_verified,
            "status": "passed"
            if all(
                [
                    is_deterministic,
                    risk_mapping_verified,
                    weights_behavior_verified,
                    score_stability_verified,
                ]
            )
            else "failed",
        }

    def run_full_evaluation(
        self,
        dataset: EvaluationDataset | dict[str, Any] | None = None,
        include_benchmarks: bool = True,
    ) -> EvaluationReport:
        """Execute complete evaluation workflow across all engine capabilities."""
        if dataset is None:
            ds = EvaluationDataset.create_synthetic_benchmark_dataset()
        elif isinstance(dataset, dict):
            ds = EvaluationDataset.from_dict(dataset)
        else:
            ds = dataset

        bm_eval = self.evaluate_blind_match(ds)
        sig_eval = self.evaluate_signals(ds)
        ano_eval = self.evaluate_anomaly_detection(ds)
        int_eval = self.evaluate_integrity_score(ds)

        bench_eval: dict[str, Any] = {}
        if include_benchmarks:
            bench_eval = self.benchmark_runner.run_full_benchmark(ds)

        # Calculate overall accuracy across components
        bm_acc = bm_eval.get("metrics", {}).get("accuracy", 1.0)
        ano_acc = ano_eval.get("metrics", {}).get("accuracy", 1.0)
        sig_f1 = sig_eval.get("f1_score", 1.0)

        summary = {
            "status": "completed",
            "blind_match_f1": bm_eval.get("metrics", {}).get("f1_score", 0.0),
            "signals_f1": sig_f1,
            "anomaly_detection_f1": ano_eval.get("metrics", {}).get("f1_score", 0.0),
            "mean_accuracy": round((bm_acc + ano_acc) / 2.0, 4),
            "integrity_consistency": int_eval.get("status", "unknown"),
        }

        return EvaluationReport(
            blind_match=bm_eval,
            signals=sig_eval,
            anomaly_detection=ano_eval,
            integrity_score=int_eval,
            benchmark=bench_eval,
            summary=summary,
            generated_at=datetime.now(UTC).isoformat(),
        )
