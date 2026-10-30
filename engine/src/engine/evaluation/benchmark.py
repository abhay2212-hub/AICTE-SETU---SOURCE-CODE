# Owner: Dev A
"""Benchmarking utilities measuring throughput and latency across engine components."""

from __future__ import annotations

import time
from typing import Any

from engine.anomaly.service import AnomalyDetectionService
from engine.blind_match.models import StudentRecord
from engine.blind_match.service import BlindMatchService
from engine.evaluation.datasets import EvaluationDataset
from engine.scoring.service import IntegrityScoringService
from engine.signals import execute_signals


class BenchmarkRunner:
    """Measures latency, throughput, and performance of all intelligence engine components."""

    def __init__(
        self,
        runs: int = 1,
        secret: str = "benchmark-secret-key-32b-length",
    ) -> None:
        self.runs = max(1, runs)
        self.secret = secret

    def benchmark_encoding(
        self,
        records: list[dict[str, Any]],
        secret: str = "benchmark-secret-key-32b-length",
    ) -> dict[str, Any]:
        """Measure Bloom-filter encoding time and throughput."""
        if not records:
            return {"encoding_time_ms": 0.0, "throughput_records_sec": 0.0, "total_records": 0}

        students = [
            StudentRecord(
                student_id=str(r.get("student_id", f"s-{i}")),
                institution_id=str(r.get("institution_id", "inst")),
                student_name=str(r.get("student_name", "Student")),
                dob=str(r.get("dob", "2004-01-01")),
                father_name=str(r.get("father_name", "")),
                mother_name=str(r.get("mother_name", "")),
                apaar_id=r.get("apaar_id"),
            )
            for i, r in enumerate(records)
        ]

        service = BlindMatchService(secret=secret)

        latencies: list[float] = []
        for _ in range(self.runs):
            t0 = time.perf_counter()
            for s in students:
                service.encode_student(s)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        mean_ms = sum(latencies) / len(latencies)
        throughput = (len(students) / (mean_ms / 1000.0)) if mean_ms > 0 else 0.0

        return {
            "encoding_time_ms": round(mean_ms, 3),
            "latency_per_record_ms": round(mean_ms / len(students), 4),
            "throughput_records_sec": round(throughput, 1),
            "total_records": len(students),
        }

    def benchmark_linkage(
        self,
        records: list[dict[str, Any]],
        threshold: float = 0.85,
    ) -> dict[str, Any]:
        """Measure pairwise Dice similarity linkage and candidate duplicate detection."""
        if not records:
            return {"linkage_time_ms": 0.0, "candidate_pairs_found": 0}

        students = [
            StudentRecord(
                student_id=str(r.get("student_id", f"s-{i}")),
                institution_id=str(r.get("institution_id", f"inst-{i % 3}")),
                student_name=str(r.get("student_name", "Student")),
                dob=str(r.get("dob", "2004-01-01")),
                father_name=str(r.get("father_name", "")),
                mother_name=str(r.get("mother_name", "")),
                apaar_id=r.get("apaar_id"),
            )
            for i, r in enumerate(records)
        ]

        service = BlindMatchService(secret=self.secret, threshold=threshold)

        latencies: list[float] = []
        matches_found = 0
        for _ in range(self.runs):
            t0 = time.perf_counter()
            matches = service.run_blind_match(students, threshold=threshold)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)
            matches_found = len(matches)

        mean_ms = sum(latencies) / len(latencies)

        return {
            "linkage_time_ms": round(mean_ms, 3),
            "candidate_pairs_found": matches_found,
            "total_records": len(students),
        }

    def benchmark_signals(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Measure rule-based integrity signal execution time."""
        admissions = payload.get("admissions") or payload.get("records") or []

        latencies: list[float] = []
        signals_count = 0
        for _ in range(self.runs):
            t0 = time.perf_counter()
            sigs = execute_signals(payload)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)
            signals_count = len(sigs)

        mean_ms = sum(latencies) / len(latencies)
        throughput = (len(admissions) / (mean_ms / 1000.0)) if mean_ms > 0 else 0.0

        return {
            "signals_execution_time_ms": round(mean_ms, 3),
            "signals_generated": signals_count,
            "admissions_evaluated": len(admissions),
            "throughput_admissions_sec": round(throughput, 1),
        }

    def benchmark_anomaly_detection(
        self,
        institutions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Measure Isolation Forest anomaly detection training and scoring latency."""
        if not institutions:
            return {"anomaly_detection_time_ms": 0.0, "institutions_evaluated": 0}

        service = AnomalyDetectionService(random_state=42)

        latencies: list[float] = []
        for _ in range(self.runs):
            t0 = time.perf_counter()
            service.fit_predict(institutions)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        mean_ms = sum(latencies) / len(latencies)

        return {
            "anomaly_detection_time_ms": round(mean_ms, 3),
            "institutions_evaluated": len(institutions),
            "latency_per_institution_ms": round(mean_ms / len(institutions), 4),
        }

    def benchmark_integrity_score(
        self,
        institutions_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Measure Integrity Score calculation throughput."""
        if not institutions_data:
            return {"integrity_score_time_ms": 0.0, "institutions_scored": 0}

        service = IntegrityScoringService()

        latencies: list[float] = []
        for _ in range(self.runs):
            t0 = time.perf_counter()
            service.calculate_batch(institutions_data)
            t1 = time.perf_counter()
            latencies.append((t1 - t0) * 1000.0)

        mean_ms = sum(latencies) / len(latencies)

        return {
            "integrity_score_time_ms": round(mean_ms, 3),
            "institutions_scored": len(institutions_data),
            "latency_per_institution_ms": round(mean_ms / len(institutions_data), 4),
        }

    def run_full_benchmark(self, dataset: EvaluationDataset) -> dict[str, Any]:
        """Execute comprehensive multi-stage benchmarking across all engine pipelines."""
        t_enc = self.benchmark_encoding(dataset.blind_match_records)
        t_link = self.benchmark_linkage(dataset.blind_match_records)
        t_sig = self.benchmark_signals(dataset.signals_data)
        t_ano = self.benchmark_anomaly_detection(dataset.anomaly_institutions)
        t_score = self.benchmark_integrity_score(dataset.integrity_institutions)

        total_ms = (
            t_enc.get("encoding_time_ms", 0.0)
            + t_link.get("linkage_time_ms", 0.0)
            + t_sig.get("signals_execution_time_ms", 0.0)
            + t_ano.get("anomaly_detection_time_ms", 0.0)
            + t_score.get("integrity_score_time_ms", 0.0)
        )

        return {
            "encoding": t_enc,
            "linkage": t_link,
            "signals": t_sig,
            "anomaly_detection": t_ano,
            "integrity_score": t_score,
            "total_benchmark_time_ms": round(total_ms, 3),
        }
