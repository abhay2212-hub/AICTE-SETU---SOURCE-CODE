# Owner: Dev A
"""Evaluation dataset formats and ground-truth loaders."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EvaluationDataset:
    """Standardized, reusable dataset format for engine evaluation and benchmarking."""

    dataset_id: str = "dataset-default"
    name: str = "Standard Evaluation Dataset"
    description: str = "Ground truth labelled dataset for APAAR Integrity Platform evaluation."

    # 1. Blind Match evaluation data
    blind_match_records: list[dict[str, Any]] = field(default_factory=list)
    blind_match_ground_truth: list[dict[str, Any]] = field(default_factory=list)

    # 2. Rule signals evaluation data
    signals_data: dict[str, Any] = field(default_factory=dict)
    signals_ground_truth: list[dict[str, Any]] = field(default_factory=list)

    # 3. Anomaly detection evaluation data
    anomaly_institutions: list[dict[str, Any]] = field(default_factory=list)
    anomaly_ground_truth: dict[str, bool] = field(default_factory=dict)

    # 4. Integrity score evaluation data
    integrity_institutions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize dataset to a JSON-compatible dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "description": self.description,
            "blind_match": {
                "records": self.blind_match_records,
                "ground_truth": self.blind_match_ground_truth,
            },
            "signals": {
                "data": self.signals_data,
                "ground_truth": self.signals_ground_truth,
            },
            "anomaly_detection": {
                "institutions": self.anomaly_institutions,
                "ground_truth": self.anomaly_ground_truth,
            },
            "integrity_score": {
                "institutions": self.integrity_institutions,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize dataset to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, file_path: str | Path) -> None:
        """Save dataset to a local JSON file."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationDataset:
        """Construct an EvaluationDataset from a dictionary."""
        if not data:
            return cls()

        bm_data = data.get("blind_match", {})
        sig_data = data.get("signals", {})
        ano_data = data.get("anomaly_detection", {})
        int_data = data.get("integrity_score", {})

        # Handle flat or nested keys
        bm_records = bm_data.get("records") or data.get("blind_match_records") or []
        bm_gt = bm_data.get("ground_truth") or data.get("blind_match_ground_truth") or []

        s_data = sig_data.get("data") or data.get("signals_data") or {}
        s_gt = sig_data.get("ground_truth") or data.get("signals_ground_truth") or []

        a_inst = ano_data.get("institutions") or data.get("anomaly_institutions") or []
        a_gt = ano_data.get("ground_truth") or data.get("anomaly_ground_truth") or {}
        if isinstance(a_gt, list):
            # Convert list of {"institution_id": "...", "is_anomalous": True} to dict
            a_gt = {
                item["institution_id"]: bool(item.get("is_anomalous", False))
                for item in a_gt
                if isinstance(item, dict) and "institution_id" in item
            }

        i_inst = int_data.get("institutions") or data.get("integrity_institutions") or []

        return cls(
            dataset_id=str(data.get("dataset_id") or "dataset-custom"),
            name=str(data.get("name") or "Custom Evaluation Dataset"),
            description=str(data.get("description") or ""),
            blind_match_records=bm_records,
            blind_match_ground_truth=bm_gt,
            signals_data=s_data,
            signals_ground_truth=s_gt,
            anomaly_institutions=a_inst,
            anomaly_ground_truth=a_gt,
            integrity_institutions=i_inst,
        )

    @classmethod
    def from_json(cls, json_str: str) -> EvaluationDataset:
        """Load an EvaluationDataset from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def from_file(cls, file_path: str | Path) -> EvaluationDataset:
        """Load an EvaluationDataset from a local JSON file."""
        content = Path(file_path).read_text(encoding="utf-8")
        return cls.from_json(content)

    @classmethod
    def create_synthetic_benchmark_dataset(cls, seed: int = 42) -> EvaluationDataset:
        """Generate a complete, reproducible in-memory ground-truth evaluation dataset."""
        # 1. Blind Match records with planted duplicates
        bm_records: list[dict[str, Any]] = []
        bm_gt: list[dict[str, Any]] = []

        # Pair 1: Exact APAAR duplicate across institutions
        bm_records.append(
            {
                "student_id": "bm-stu-1a",
                "institution_id": "inst-A",
                "student_name": "Aarav Sharma",
                "dob": "2004-05-15",
                "father_name": "Vijay Sharma",
                "mother_name": "Sunita Sharma",
                "apaar_id": "999900001111",
            }
        )
        bm_records.append(
            {
                "student_id": "bm-stu-1b",
                "institution_id": "inst-B",
                "student_name": "Aarav Sharma",
                "dob": "2004-05-15",
                "father_name": "Vijay Sharma",
                "mother_name": "Sunita Sharma",
                "apaar_id": "999900001111",
            }
        )
        bm_gt.append(
            {
                "student_a_id": "bm-stu-1a",
                "student_b_id": "bm-stu-1b",
                "is_duplicate": True,
                "type": "exact_apaar",
            }
        )

        # Pair 2: Fuzzy typo duplicate across institutions
        bm_records.append(
            {
                "student_id": "bm-stu-2a",
                "institution_id": "inst-A",
                "student_name": "Priyanka Joshi",
                "dob": "2004-07-20",
                "father_name": "Kailash Joshi",
                "mother_name": "Meena Joshi",
            }
        )
        bm_records.append(
            {
                "student_id": "bm-stu-2b",
                "institution_id": "inst-C",
                "student_name": "Priyannka Joshi",  # single character typo
                "dob": "2004-07-20",
                "father_name": "Kailash Joshi",
                "mother_name": "Meena Joshi",
            }
        )
        bm_gt.append(
            {
                "student_a_id": "bm-stu-2a",
                "student_b_id": "bm-stu-2b",
                "is_duplicate": True,
                "type": "fuzzy_typo",
            }
        )

        # Non-duplicate pairs (same birth year block to test discrimination)
        bm_records.append(
            {
                "student_id": "bm-stu-distinct-1",
                "institution_id": "inst-B",
                "student_name": "Rohan Verma",
                "dob": "2004-01-10",
                "father_name": "Suresh Verma",
                "mother_name": "Anita Verma",
            }
        )
        bm_records.append(
            {
                "student_id": "bm-stu-distinct-2",
                "institution_id": "inst-C",
                "student_name": "Deepak Mehta",
                "dob": "2004-11-25",
                "father_name": "Ramesh Mehta",
                "mother_name": "Kavita Mehta",
            }
        )
        bm_gt.append(
            {
                "student_a_id": "bm-stu-distinct-1",
                "student_b_id": "bm-stu-distinct-2",
                "is_duplicate": False,
                "type": "non_duplicate",
            }
        )

        # 2. Signals data with planted rule violations
        admissions: list[dict[str, Any]] = [
            # Eligibility violator: qualifying marks below 45% norm
            {
                "student_id": "sig-stu-elig",
                "institution_id": "inst-violator",
                "programme_code": "BTECH_CSE",
                "category": "general",
                "qualifying_exam_pct": 36.5,
                "dob": "2005-03-12",
                "admission_date": "2023-08-01",
                "upload_date": "2023-08-05",
                "contact_phone": "9811122233",
            },
            # Backdated admission: upload delay > 30 days
            {
                "student_id": "sig-stu-backdated",
                "institution_id": "inst-violator",
                "programme_code": "BTECH_ECE",
                "category": "general",
                "qualifying_exam_pct": 68.0,
                "dob": "2004-06-18",
                "admission_date": "2023-01-15",
                "upload_date": "2023-04-20",  # 95 days delay
                "contact_phone": "9822233344",
            },
            # Shared contact cluster students
            {
                "student_id": "sig-stu-cluster-1",
                "institution_id": "inst-violator",
                "contact_phone": "9990001111",
            },
            {
                "student_id": "sig-stu-cluster-2",
                "institution_id": "inst-other",
                "contact_phone": "9990001111",
            },
            # Clean admission
            {
                "student_id": "sig-stu-clean",
                "institution_id": "inst-clean",
                "programme_code": "BTECH_CSE",
                "category": "general",
                "qualifying_exam_pct": 82.0,
                "dob": "2005-01-10",
                "admission_date": "2023-08-01",
                "upload_date": "2023-08-05",
                "contact_phone": "9877766655",
            },
        ]

        historical_stats = [
            # Zero attrition repeated cap filling
            {
                "institution_id": "inst-cap-filler",
                "academic_year": "2021-22",
                "approved_seats": 100,
                "enrolled_students": 100,
                "attrition_count": 0,
            },
            {
                "institution_id": "inst-cap-filler",
                "academic_year": "2022-23",
                "approved_seats": 100,
                "enrolled_students": 100,
                "attrition_count": 0,
            },
        ]

        signals_data = {
            "admissions": admissions,
            "historical_stats": historical_stats,
        }

        signals_gt = [
            {
                "institution_id": "inst-violator",
                "signal_name": "ELIGIBILITY_VIOLATION",
                "student_id": "sig-stu-elig",
            },
            {
                "institution_id": "inst-violator",
                "signal_name": "BACKDATED_ADMISSIONS",
                "student_id": "sig-stu-backdated",
            },
            {
                "institution_id": "inst-violator",
                "signal_name": "SHARED_CONTACT_CLUSTER",
            },
            {
                "institution_id": "inst-cap-filler",
                "signal_name": "ZERO_ATTRITION_CAP_FILLING",
            },
        ]

        # 3. Anomaly detection institutions (10 normal + 2 planted outliers)
        anomaly_insts: list[dict[str, Any]] = []
        anomaly_gt: dict[str, bool] = {}

        for i in range(10):
            inst_id = f"eval-inst-normal-{i}"
            anomaly_insts.append(
                {
                    "institution_id": inst_id,
                    "features": {
                        "seat_utilisation": 0.70 + (i % 4) * 0.05,
                        "intake_growth": 0.02,
                        "duplicate_rate": 0.0,
                        "blind_match_rate": 0.01,
                        "shared_contact_rate": 0.02,
                        "backdated_admission_rate": 0.01,
                        "eligibility_violation_count": 0.0,
                        "zero_attrition_frequency": 0.0,
                        "average_signal_severity": 1.0,
                        "total_signals_generated": 1.0,
                    },
                }
            )
            anomaly_gt[inst_id] = False

        # Outlier 1: extreme seat overrun and duplicate rate
        anomaly_insts.append(
            {
                "institution_id": "eval-inst-outlier-1",
                "features": {
                    "seat_utilisation": 2.45,
                    "intake_growth": 1.80,
                    "duplicate_rate": 0.65,
                    "blind_match_rate": 0.40,
                    "shared_contact_rate": 0.50,
                    "backdated_admission_rate": 0.75,
                    "eligibility_violation_count": 45.0,
                    "zero_attrition_frequency": 1.0,
                    "average_signal_severity": 4.0,
                    "total_signals_generated": 18.0,
                },
            }
        )
        anomaly_gt["eval-inst-outlier-1"] = True

        # Outlier 2: massive backdated admission and eligibility violations
        anomaly_insts.append(
            {
                "institution_id": "eval-inst-outlier-2",
                "features": {
                    "seat_utilisation": 1.95,
                    "intake_growth": 1.10,
                    "duplicate_rate": 0.35,
                    "blind_match_rate": 0.30,
                    "shared_contact_rate": 0.40,
                    "backdated_admission_rate": 0.90,
                    "eligibility_violation_count": 60.0,
                    "zero_attrition_frequency": 1.0,
                    "average_signal_severity": 3.8,
                    "total_signals_generated": 14.0,
                },
            }
        )
        anomaly_gt["eval-inst-outlier-2"] = True

        # 4. Integrity score institutions
        integrity_insts: list[dict[str, Any]] = [
            {"institution_id": "eval-score-clean", "anomaly_score": 0.05, "signals": []},
            {
                "institution_id": "eval-score-medium",
                "anomaly_score": 0.35,
                "signals": [{"signal_name": "ELIGIBILITY_VIOLATION", "severity": "review"}],
            },
            {
                "institution_id": "eval-score-critical",
                "anomaly_score": 0.95,
                "signals": [
                    {"signal_name": "BACKDATED_ADMISSIONS", "severity": "error"},
                    {"signal_name": "SHARED_CONTACT_CLUSTER", "severity": "error"},
                ],
            },
        ]

        return cls(
            dataset_id=f"benchmark-synthetic-seed-{seed}",
            name="Synthetic Intelligence Engine Ground Truth Benchmark",
            description="Reproducible multi-domain ground-truth dataset with planted anomalies.",
            blind_match_records=bm_records,
            blind_match_ground_truth=bm_gt,
            signals_data=signals_data,
            signals_ground_truth=signals_gt,
            anomaly_institutions=anomaly_insts,
            anomaly_ground_truth=anomaly_gt,
            integrity_institutions=integrity_insts,
        )
