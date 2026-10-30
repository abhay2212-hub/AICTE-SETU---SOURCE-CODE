# Owner: Dev A
"""Comprehensive tests for engine benchmarking utilities."""

from __future__ import annotations

from engine.evaluation.benchmark import BenchmarkRunner
from engine.evaluation.datasets import EvaluationDataset


def test_benchmark_encoding() -> None:
    runner = BenchmarkRunner(runs=1)
    records = [
        {
            "student_id": f"s-{i}",
            "institution_id": "inst-1",
            "student_name": "Test Student",
            "dob": "2004-05-15",
            "father_name": "Father",
            "mother_name": "Mother",
        }
        for i in range(10)
    ]

    res = runner.benchmark_encoding(records)
    assert "encoding_time_ms" in res
    assert res["total_records"] == 10
    assert res["latency_per_record_ms"] >= 0.0
    assert res["throughput_records_sec"] >= 0.0


def test_benchmark_linkage() -> None:
    runner = BenchmarkRunner(runs=1)
    records = [
        {
            "student_id": "s-1",
            "institution_id": "inst-1",
            "student_name": "Aarav Sharma",
            "dob": "2004-05-15",
            "apaar_id": "999900001111",
        },
        {
            "student_id": "s-2",
            "institution_id": "inst-2",
            "student_name": "Aarav Sharma",
            "dob": "2004-05-15",
            "apaar_id": "999900001111",
        },
    ]

    res = runner.benchmark_linkage(records, threshold=0.85)
    assert "linkage_time_ms" in res
    assert res["candidate_pairs_found"] >= 1
    assert res["total_records"] == 2


def test_benchmark_signals() -> None:
    runner = BenchmarkRunner(runs=1)
    payload = {
        "admissions": [
            {
                "student_id": "s-1",
                "institution_id": "inst-1",
                "category": "general",
                "qualifying_exam_pct": 35.0,  # Below 45% norm
                "dob": "2005-01-01",
                "admission_date": "2023-08-01",
            }
        ]
    }

    res = runner.benchmark_signals(payload)
    assert "signals_execution_time_ms" in res
    assert res["signals_generated"] >= 1
    assert res["admissions_evaluated"] == 1


def test_benchmark_anomaly_detection() -> None:
    runner = BenchmarkRunner(runs=1)
    institutions = [
        {"institution_id": f"inst-{i}", "seat_utilisation": 0.8, "duplicate_rate": 0.01}
        for i in range(5)
    ]

    res = runner.benchmark_anomaly_detection(institutions)
    assert "anomaly_detection_time_ms" in res
    assert res["institutions_evaluated"] == 5


def test_benchmark_integrity_score() -> None:
    runner = BenchmarkRunner(runs=1)
    institutions = [
        {"institution_id": "inst-1", "anomaly_score": 0.2, "signals": []},
        {"institution_id": "inst-2", "anomaly_score": 0.8, "signals": []},
    ]

    res = runner.benchmark_integrity_score(institutions)
    assert "integrity_score_time_ms" in res
    assert res["institutions_scored"] == 2


def test_run_full_benchmark_on_synthetic_dataset() -> None:
    dataset = EvaluationDataset.create_synthetic_benchmark_dataset()
    runner = BenchmarkRunner(runs=1)

    res = runner.run_full_benchmark(dataset)
    assert "encoding" in res
    assert "linkage" in res
    assert "signals" in res
    assert "anomaly_detection" in res
    assert "integrity_score" in res
    assert "total_benchmark_time_ms" in res
    assert res["total_benchmark_time_ms"] > 0.0
