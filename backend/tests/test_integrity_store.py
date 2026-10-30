# Owner: Dev B
"""Input checks of app.services.integrity_store (the upsert itself is an integration test)."""

from __future__ import annotations

import pytest

from app.services import integrity_store


class NoDb:
    def cursor(self):
        raise AssertionError("nothing should be written")


def test_missing_required_key_writes_nothing():
    result = {"institution_id": "x", "academic_year": "2026-27", "score": 1, "tier": "low"}
    with pytest.raises(ValueError, match="model_version"):
        integrity_store.save_results(NoDb(), [result])


def test_empty_list_writes_nothing():
    assert integrity_store.save_results(NoDb(), []) == 0


def test_latest_rankings_sorting_and_signals():
    class FakeConn:
        def execute(self, query, params=()):
            class FakeCursor:
                def fetchall(self):
                    return [
                        {
                            "institution_id": "inst-1",
                            "institution_name": "Inst Clean",
                            "aicte_code": "1-001",
                            "integrity_score": 95.0,
                            "tier": "low",
                            "components": {"anomaly_score": 0.15},
                            "top_features": [],
                            "signals": [],
                            "computed_at": "2026-10-24T06:00:00Z",
                        },
                        {
                            "institution_id": "inst-bharatpur",
                            "institution_name": "Bharatpur Institute",
                            "aicte_code": "1-004",
                            "integrity_score": 80.24,
                            "tier": "medium",
                            "components": {"anomaly_score": 0.70},
                            "top_features": [],
                            "signals": [],
                            "computed_at": "2026-10-24T06:00:00Z",
                        },
                        {
                            "institution_id": "inst-ujjain",
                            "institution_name": "Ujjain College",
                            "aicte_code": "1-003",
                            "integrity_score": 58.57,
                            "tier": "high",
                            "components": {"anomaly_score": 0.50},
                            "top_features": [],
                            "signals": [],
                            "computed_at": "2026-10-24T06:00:00Z",
                        },
                        {
                            "institution_id": "inst-2",
                            "institution_name": "Inst Risky (Shadow)",
                            "aicte_code": "1-002",
                            "integrity_score": 35.0,
                            "tier": "critical",
                            "components": {"anomaly": 0.85},
                            "top_features": [],
                            "signals": [
                                {"code": "INTAKE_OVERRUN"},
                                {"code": "SHARED_CONTACT"},
                                {"code": "INTAKE_OVERRUN"},  # duplicate code to test deduplication
                            ],
                            "computed_at": "2026-10-24T06:00:00Z",
                        },
                    ]

            return FakeCursor()

    rankings = integrity_store.latest_rankings(FakeConn(), "2026-27")
    assert len(rankings) == 4
    # Rankings sorted by integrity score lowest first:
    # 1. Shadow (35.0)
    assert rankings[0]["rank"] == 1
    assert rankings[0]["institution_id"] == "inst-2"
    assert rankings[0]["integrity_score"] == 35.0
    assert rankings[0]["anomaly_score"] == 0.85
    assert rankings[0]["top_signals"] == ["INTAKE_OVERRUN", "SHARED_CONTACT"]

    # 2. Ujjain (58.57) ranks before Bharatpur (80.24) despite lower anomaly score
    assert rankings[1]["rank"] == 2
    assert rankings[1]["institution_id"] == "inst-ujjain"
    assert rankings[1]["integrity_score"] == 58.57
    assert rankings[1]["anomaly_score"] == 0.50

    # 3. Bharatpur (80.24)
    assert rankings[2]["rank"] == 3
    assert rankings[2]["institution_id"] == "inst-bharatpur"
    assert rankings[2]["integrity_score"] == 80.24
    assert rankings[2]["anomaly_score"] == 0.70

    # 4. Clean (95.0)
    assert rankings[3]["rank"] == 4
    assert rankings[3]["institution_id"] == "inst-1"
    assert rankings[3]["integrity_score"] == 95.0
    assert rankings[3]["anomaly_score"] == 0.15
    assert rankings[3]["top_signals"] == []
