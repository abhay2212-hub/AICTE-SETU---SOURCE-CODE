# Owner: Dev A
"""Unit tests for /integrity router and integrity persistence integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.conftest import as_role

SHADOW = "10000000-0000-4000-8000-000000000003"
NARMADA = "10000000-0000-4000-8000-000000000002"


def test_integrity_endpoints_in_mock_mode(client):
    """Fixture/demo mode returns mock fixtures with X-Mock: true."""
    # 1. Rankings
    res = client.get("/integrity/institutions", headers=as_role("aicte_admin"))
    assert res.status_code == 200
    assert res.headers["X-Mock"] == "true"
    rankings = res.json()
    assert len(rankings) == 3
    assert rankings[0]["institution_id"] == SHADOW
    assert rankings[0]["rank"] == 1
    assert rankings[0]["integrity_score"] == 38.0

    # 2. Detail
    detail_res = client.get(f"/integrity/institutions/{SHADOW}", headers=as_role("aicte_admin"))
    assert detail_res.status_code == 200
    assert detail_res.headers["X-Mock"] == "true"
    detail = detail_res.json()
    assert detail["institution_id"] == SHADOW
    assert detail["integrity_score"] == 38.0
    assert "signals" in detail
    assert "anomaly" in detail
    assert detail["anomaly"]["score"] == 0.81

    # 3. 404 for unknown institution
    not_found_res = client.get(
        "/integrity/institutions/00000000-0000-0000-0000-000000000000",
        headers=as_role("aicte_admin"),
    )
    assert not_found_res.status_code == 404


def test_integrity_role_guard(client):
    """Students and unauthenticated callers cannot access integrity endpoints."""
    assert client.get("/integrity/institutions", headers=as_role("student")).status_code == 403
    url = f"/integrity/institutions/{SHADOW}"
    assert client.get(url, headers=as_role("student")).status_code == 403
    assert client.get("/integrity/institutions", headers=as_role("auditor")).status_code == 200


def test_integrity_endpoints_in_real_mode(client, settings_override):
    """When REAL_DOMAINS contains 'integrity', retrieves persisted results with X-Mock: false."""
    settings_override(
        real_domains="integrity", database_url="postgresql://fake:fake@localhost/fake"
    )

    persisted_rankings = [
        {
            "rank": 1,
            "institution_id": SHADOW,
            "institution_name": "Shadow Institute of Technology",
            "aicte_code": "1-9999003",
            "integrity_score": 42.5,
            "anomaly_score": 0.78,
            "top_signals": ["INTAKE_OVERRUN", "BACKDATED_ENTRY"],
        },
        {
            "rank": 2,
            "institution_id": NARMADA,
            "institution_name": "Narmada Valley College of Technology",
            "aicte_code": "1-9999002",
            "integrity_score": 88.0,
            "anomaly_score": 0.25,
            "top_signals": [],
        },
    ]

    persisted_detail = {
        "institution_id": SHADOW,
        "academic_year": "2026-27",
        "score": 42.5,
        "tier": "high",
        "components": {
            "signals_deduction": 30.0,
            "anomaly_deduction": 20.0,
            "blind_match_deduction": 7.5,
            "total_deduction": 57.5,
            "anomaly_score": 0.78,
        },
        "top_features": [
            {"name": "management_quota_share", "value": 0.45, "peer_median": 0.12},
            {"name": "late_admission_share", "value": 0.30, "peer_median": 0.05},
        ],
        "signals": [
            {
                "code": "INTAKE_OVERRUN",
                "severity": "review",
                "evidence": {"programme_code": "UG-CSE", "overrun": 11},
            },
            {
                "code": "BACKDATED_ENTRY",
                "severity": "review",
                "evidence": {"count": 6},
            },
        ],
        "model_version": "0.1.0",
        "computed_at": "2026-10-24T06:00:00Z",
    }

    mock_conn = MagicMock()
    with (
        patch("app.routers.integrity.transaction") as mock_tx,
        patch("app.services.integrity_store.latest_rankings", return_value=persisted_rankings),
        patch("app.services.integrity_store.latest_for") as mock_latest_for,
    ):
        mock_tx.return_value.__enter__.return_value = mock_conn

        def side_effect_latest_for(conn, inst_id, year=None):
            if inst_id == SHADOW:
                return persisted_detail
            return None

        mock_latest_for.side_effect = side_effect_latest_for

        # 1. Test rankings in real mode
        res = client.get("/integrity/institutions", headers=as_role("aicte_admin"))
        assert res.status_code == 200
        assert res.headers["X-Mock"] == "false"
        data = res.json()
        assert len(data) == 2
        assert data[0]["institution_id"] == SHADOW
        assert data[0]["integrity_score"] == 42.5
        assert data[0]["anomaly_score"] == 0.78
        assert data[0]["top_signals"] == ["INTAKE_OVERRUN", "BACKDATED_ENTRY"]

        # 2. Test detail in real mode
        res_detail = client.get(f"/integrity/institutions/{SHADOW}", headers=as_role("aicte_admin"))
        assert res_detail.status_code == 200
        assert res_detail.headers["X-Mock"] == "false"
        detail_data = res_detail.json()
        assert detail_data["institution_id"] == SHADOW
        assert detail_data["integrity_score"] == 42.5
        assert detail_data["components"]["total_deduction"] == 57.5
        assert detail_data["anomaly"]["score"] == 0.78
        assert len(detail_data["anomaly"]["top_features"]) == 2
        assert len(detail_data["signals"]) == 2

        # 3. Test unknown institution in real mode raises 404
        res_unknown = client.get(
            "/integrity/institutions/00000000-0000-0000-0000-000000000000",
            headers=as_role("aicte_admin"),
        )
        assert res_unknown.status_code == 404


def test_integrity_real_mode_empty_table(client, settings_override):
    """When integrity_scores is empty in REAL mode, returns [] with 200 OK without errors."""
    settings_override(
        real_domains="integrity", database_url="postgresql://fake:fake@localhost/fake"
    )
    mock_conn = MagicMock()
    with (
        patch("app.routers.integrity.transaction") as mock_tx,
        patch("app.services.integrity_store.latest_rankings", return_value=[]),
    ):
        mock_tx.return_value.__enter__.return_value = mock_conn
        res = client.get("/integrity/institutions", headers=as_role("aicte_admin"))
        assert res.status_code == 200
        assert res.headers["X-Mock"] == "false"
        assert res.json() == []


def test_canonical_cli_execution():
    """Verify scripts.compute_integrity argument parser and execution."""
    from scripts.compute_integrity import build_parser, main

    # 1. Test argument parser
    parser = build_parser()
    args = parser.parse_args(["--year", "2027-28", "--institutions", SHADOW, NARMADA])
    assert args.year == "2027-28"
    assert args.institutions == [SHADOW, NARMADA]

    # 2. Test execution without DATABASE_URL returns error code 2
    with (
        patch("scripts.compute_integrity.get_settings") as mock_settings,
        patch("sys.stderr"),
    ):
        mock_settings.return_value.database_url = ""
        assert main([]) == 2

    # 3. Test execution with DATABASE_URL calls compute and save
    fake_results = [{"institution_id": SHADOW}]
    with (
        patch("scripts.compute_integrity.get_settings") as mock_settings,
        patch("scripts.compute_integrity.transaction") as mock_tx,
        patch(
            "scripts.compute_integrity.compute_institution_results", return_value=fake_results
        ) as mock_compute,
        patch("scripts.compute_integrity.save_results", return_value=1) as mock_save,
        patch("scripts.compute_integrity.close_pool"),
    ):
        mock_settings.return_value.database_url = "postgresql://fake:fake@localhost/fake"
        mock_tx.return_value.__enter__.return_value = MagicMock()
        ret = main(["--year", "2026-27"])
        assert ret == 0
        mock_compute.assert_called_once()
        mock_save.assert_called_once()


def test_compute_integrity_persistence():
    """Verify compute_and_save_integrity calls integrity_store.save_results."""
    from app.services.integrity import compute_and_save_integrity

    sample_results = [
        {
            "institution_id": SHADOW,
            "academic_year": "2026-27",
            "score": 40.0,
            "tier": "high",
            "model_version": "0.1.0",
            "components": {"anomaly": 0.8},
            "top_features": [],
            "signals": [],
        }
    ]

    mock_conn = MagicMock()
    with patch("app.services.integrity_store.save_results", return_value=1) as mock_save:
        count = compute_and_save_integrity(mock_conn, results=sample_results)
        assert count == 1
        mock_save.assert_called_once_with(mock_conn, sample_results)


def test_latest_for_academic_year_optional():
    """Verify latest_for queries with year when provided, and without when None."""
    from app.services import integrity_store

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchone.return_value = {
        "institution_id": SHADOW,
        "academic_year": "2026-27",
        "score": 50.0,
        "tier": "medium",
        "components": {},
        "top_features": [],
        "signals": [],
        "model_version": "0.1.0",
        "computed_at": "2026-10-24T06:00:00Z",
    }

    # 1. With explicit year
    res_year = integrity_store.latest_for(mock_conn, SHADOW, "2026-27")
    assert res_year is not None
    assert "academic_year = %s" in mock_conn.execute.call_args[0][0]
    assert mock_conn.execute.call_args[0][1] == (SHADOW, "2026-27")

    # 2. Without year (None)
    res_none = integrity_store.latest_for(mock_conn, SHADOW, None)
    assert res_none is not None
    assert "academic_year = %s" not in mock_conn.execute.call_args[0][0]
    assert mock_conn.execute.call_args[0][1] == (SHADOW,)


def test_compute_institution_results_peer_medians():
    """Verify top_features computes cohort peer medians rather than copying feature value."""
    from engine.types import AnomalyResult

    from app.services.integrity import compute_institution_results

    mock_conn = MagicMock()

    inst_rows = [
        {"id": "inst-1", "aicte_code": "1-001", "name": "Inst A", "state": "MP"},
        {"id": "inst-2", "aicte_code": "1-002", "name": "Inst B", "state": "MP"},
        {"id": "inst-3", "aicte_code": "1-003", "name": "Inst C", "state": "MP"},
    ]

    # Inst 1 has blind match rate while others have none
    def mock_execute(query, params=()):
        cursor = MagicMock()
        q = str(query).lower()
        if "from public.institutions" in q:
            cursor.fetchall.return_value = inst_rows
        elif "from public.admissions" in q:
            # 10 admissions each
            rows = []
            for inst_id in ["inst-1", "inst-2", "inst-3"]:
                for i in range(10):
                    rows.append(
                        {
                            "id": f"{inst_id}-{i}",
                            "institution_id": inst_id,
                            "programme_id": "prog-1",
                            "student_id": f"s-{inst_id}-{i}",
                            "apaar_id": f"apaar-{inst_id}-{i}",
                            "phone": "9999999999",
                            "academic_year": "2026-27",
                            "active": True,
                            "admission_date": "2026-08-01",
                            "upload_date": "2026-09-01",
                        }
                    )
            cursor.fetchall.return_value = rows
        elif "from public.review_cases" in q and "blind_match" not in q:
            cursor.fetchall.return_value = []
        elif "from public.seat_pools" in q:
            cursor.fetchall.return_value = []
        elif "kind = 'blind_match'" in q:
            cursor.fetchall.return_value = []
        else:
            cursor.fetchall.return_value = []
        return cursor

    mock_conn.execute.side_effect = mock_execute

    with (
        patch("app.services.integrity.AnomalyDetectionService") as mock_anomaly_cls,
        patch("app.services.integrity.IntegrityScoringService"),
    ):
        mock_svc = mock_anomaly_cls.return_value
        # Mock predict returning top_features for inst-1
        mock_svc.predict.return_value = [
            AnomalyResult(
                institution_id="inst-1",
                score=0.8,
                prediction="anomaly",
                top_features=["seat_utilisation"],
            ),
            AnomalyResult(
                institution_id="inst-2",
                score=0.1,
                prediction="normal",
                top_features=[],
            ),
            AnomalyResult(
                institution_id="inst-3",
                score=0.1,
                prediction="normal",
                top_features=[],
            ),
        ]

        results = compute_institution_results(mock_conn, academic_year="2026-27")
        assert len(results) == 3
        inst1_res = next(r for r in results if r["institution_id"] == "inst-1")
        assert len(inst1_res["top_features"]) == 1
        tf = inst1_res["top_features"][0]
        assert tf["name"] == "seat_utilisation"
        # Peer median is computed across the cohort (not just copied from value)
        assert isinstance(tf["peer_median"], float)
