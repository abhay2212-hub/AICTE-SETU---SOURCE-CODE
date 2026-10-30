# Owner: Dev B
"""Bridges committed data to the engine for signals, anomaly ranking and Integrity Score."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import psycopg
from engine.anomaly.features import InstitutionFeatureExtractor
from engine.anomaly.service import AnomalyDetectionService
from engine.scoring.service import IntegrityScoringService
from engine.types import MatchCase, Signal

from app.core.config import get_settings
from app.core.db import transaction
from app.services import integrity_store


def compute_institution_results(
    conn: psycopg.Connection,
    academic_year: str = "2026-27",
    institution_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Compute integrity scores for institutions from committed database data."""
    settings = get_settings()

    if institution_ids:
        inst_rows = conn.execute(
            "select id, aicte_code, name, state from public.institutions where id = any(%s::uuid[])"
            " order by aicte_code",
            (institution_ids,),
        ).fetchall()
    else:
        inst_rows = conn.execute(
            "select id, aicte_code, name, state from public.institutions order by aicte_code"
        ).fetchall()

    if not inst_rows:
        return []

    # 1. Admissions (linked via programmes.institution_id)
    if institution_ids:
        admissions_rows = conn.execute(
            """
            select a.*, p.institution_id, s.apaar_id, s.contact_hash as phone,
                   b.created_at as upload_date
            from public.admissions a
            join public.programmes p on p.id = a.programme_id
            left join public.students s on s.id = a.student_id
            left join public.batches b on b.id = a.batch_id
            where a.academic_year = %s and a.active and p.institution_id = any(%s::uuid[])
            """,
            (academic_year, institution_ids),
        ).fetchall()
    else:
        admissions_rows = conn.execute(
            """
            select a.*, p.institution_id, s.apaar_id, s.contact_hash as phone,
                   b.created_at as upload_date
            from public.admissions a
            join public.programmes p on p.id = a.programme_id
            left join public.students s on s.id = a.student_id
            left join public.batches b on b.id = a.batch_id
            where a.academic_year = %s and a.active
            """,
            (academic_year,),
        ).fetchall()

    # 2. Review cases (intake_overrun, signal, dispute)
    if institution_ids:
        rc_rows = conn.execute(
            """
            select id, kind, title, evidence, institution_id
            from public.review_cases
            where kind != 'blind_match'
              and institution_id = any(%s::uuid[])
              and (
                evidence->>'academic_year' = %s
                or evidence->>'academic_year' is null
              )
            """,
            (institution_ids, academic_year),
        ).fetchall()
    else:
        rc_rows = conn.execute(
            """
            select id, kind, title, evidence, institution_id
            from public.review_cases
            where kind != 'blind_match'
              and (
                evidence->>'academic_year' = %s
                or evidence->>'academic_year' is null
              )
            """,
            (academic_year,),
        ).fetchall()

    # 3. Seat pools (linked via programmes.institution_id)
    if institution_ids:
        seat_pools_rows = conn.execute(
            """
            select distinct on (sp.programme_id, sp.pool)
                   sp.programme_id, p.institution_id, sp.pool::text as pool,
                   sp.approved_seats, sp.academic_year
            from public.seat_pools sp
            join public.programmes p on p.id = sp.programme_id
            where sp.academic_year = %s and p.institution_id = any(%s::uuid[])
            order by sp.programme_id, sp.pool, sp.rule_version desc
            """,
            (academic_year, institution_ids),
        ).fetchall()
    else:
        seat_pools_rows = conn.execute(
            """
            select distinct on (sp.programme_id, sp.pool)
                   sp.programme_id, p.institution_id, sp.pool::text as pool,
                   sp.approved_seats, sp.academic_year
            from public.seat_pools sp
            join public.programmes p on p.id = sp.programme_id
            where sp.academic_year = %s
            order by sp.programme_id, sp.pool, sp.rule_version desc
            """,
            (academic_year,),
        ).fetchall()

    # 4. Blind match pairs (stored on review_cases of kind blind_match)
    if institution_ids:
        inst_ids_str = [str(i) for i in institution_ids]
        bm_rows = conn.execute(
            """
            select id, evidence from public.review_cases
            where kind = 'blind_match' and evidence ? 'pair_key'
              and (
                evidence->>'institution_a_id' = any(%s) or evidence->>'institution_b_id' = any(%s)
              )
              and (
                evidence->>'academic_year_a' = %s or evidence->>'academic_year_a' is null
                or evidence->>'academic_year_b' = %s or evidence->>'academic_year_b' is null
              )
            """,
            (inst_ids_str, inst_ids_str, academic_year, academic_year),
        ).fetchall()
    else:
        bm_rows = conn.execute(
            """
            select id, evidence from public.review_cases
            where kind = 'blind_match' and evidence ? 'pair_key'
              and (
                evidence->>'academic_year_a' = %s or evidence->>'academic_year_a' is null
                or evidence->>'academic_year_b' = %s or evidence->>'academic_year_b' is null
              )
            """,
            (academic_year, academic_year),
        ).fetchall()

    # Group records by institution_id
    admissions_by_inst: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in admissions_rows:
        admissions_by_inst[str(a["institution_id"])].append(dict(a))

    rc_by_inst: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rc in rc_rows:
        rc_by_inst[str(rc["institution_id"])].append(dict(rc))

    seat_pools_by_inst: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sp in seat_pools_rows:
        seat_pools_by_inst[str(sp["institution_id"])].append(dict(sp))

    bm_by_inst: dict[str, list[MatchCase]] = defaultdict(list)
    for bm in bm_rows:
        ev = bm.get("evidence") if isinstance(bm.get("evidence"), dict) else {}
        score = float(ev.get("dice") or ev.get("similarity_score") or 1.0)
        inst_a = str(ev.get("institution_a_id") or "")
        inst_b = str(ev.get("institution_b_id") or "")
        mc = MatchCase(
            institution_a=inst_a,
            institution_b=inst_b,
            student_a_id=str(ev.get("student_a_id") or ""),
            student_b_id=str(ev.get("student_b_id") or ""),
            similarity_score=score,
            confidence=score,
            case_id=str(bm["id"]),
            matched_fields=list(ev.get("matched_on") or []),
        )
        if inst_a:
            bm_by_inst[inst_a].append(mc)
        if inst_b and inst_b != inst_a:
            bm_by_inst[inst_b].append(mc)

    institutions_data: list[dict[str, Any]] = []
    for inst in inst_rows:
        inst_id = str(inst["id"])
        rcs = rc_by_inst.get(inst_id, [])

        signals: list[Signal] = []
        for rc in rcs:
            ev = rc.get("evidence") if isinstance(rc.get("evidence"), dict) else {}
            code = str(ev.get("rule_code") or ev.get("code") or rc.get("kind", "").upper())
            severity = (
                "error"
                if rc.get("kind") in ("intake_overrun", "overrun")
                else "review"
                if "DUP" in code or "CLUSTER" in code
                else "warning"
            )
            signals.append(
                Signal(
                    code=code,
                    signal_name=code,
                    institution_id=inst_id,
                    severity=severity,
                    evidence=ev,
                    description=str(rc.get("title") or ""),
                )
            )

        institutions_data.append(
            {
                "institution_id": inst_id,
                "inst": inst,
                "admissions": admissions_by_inst.get(inst_id, []),
                "signals": signals,
                "seat_pools": seat_pools_by_inst.get(inst_id, []),
                "blind_matches": bm_by_inst.get(inst_id, []),
            }
        )

    extractor = InstitutionFeatureExtractor()
    feature_vectors = [extractor.extract(d["institution_id"], d) for d in institutions_data]

    anomaly_service = AnomalyDetectionService()
    try:
        anomaly_service.fit(feature_vectors)
        anomaly_results = anomaly_service.predict(feature_vectors)
        anomaly_by_id = {a.institution_id: a for a in anomaly_results}
    except Exception:
        anomaly_by_id = {}

    scoring_service = IntegrityScoringService()
    computed_results: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    # Compute peer medians across all institutions in the evaluated cohort
    peer_medians: dict[str, float] = {}
    if feature_vectors:
        feat_values: dict[str, list[float]] = defaultdict(list)
        for fv in feature_vectors:
            for k, v in fv.to_dict().items():
                feat_values[k].append(float(v))
        for k, v_list in feat_values.items():
            if v_list:
                peer_medians[k] = round(float(statistics.median(v_list)), 4)

    for idx, item in enumerate(institutions_data):
        inst_id = item["institution_id"]
        anomaly_res = anomaly_by_id.get(inst_id)
        score_res = scoring_service.calculate(
            institution_id=inst_id,
            signals=item["signals"],
            anomaly=anomaly_res,
            blind_matches=item["blind_matches"],
        )

        anomaly_score = float(anomaly_res.score) if anomaly_res else 0.0

        top_features: list[dict[str, Any]] = []
        if anomaly_res and getattr(anomaly_res, "top_features", None):
            feat_dict = feature_vectors[idx].to_dict()
            for feat_name in anomaly_res.top_features:
                val = float(feat_dict.get(feat_name, 0.0))
                med = float(peer_medians.get(feat_name, val))
                top_features.append(
                    {
                        "name": feat_name,
                        "value": val,
                        "peer_median": med,
                    }
                )

        signals_out = [
            {
                "code": s.code,
                "severity": s.severity,
                "evidence": s.evidence,
            }
            for s in item["signals"]
        ]

        computed_results.append(
            {
                "institution_id": inst_id,
                "academic_year": academic_year,
                "score": float(score_res.score),
                "tier": str(score_res.risk_level),
                "model_version": settings.model_version,
                "components": {
                    **{k: float(v) for k, v in score_res.components.items()},
                    "anomaly_score": round(anomaly_score, 2),
                    "anomaly": round(anomaly_score, 2),
                },
                "top_features": top_features,
                "signals": signals_out,
                "computed_at": now,
            }
        )

    return computed_results


def compute_and_save_integrity(
    conn: psycopg.Connection,
    results: list[dict[str, Any]] | None = None,
    academic_year: str = "2026-27",
) -> int:
    """Store computed results via integrity_store.save_results (computing if not provided)."""
    if results is None:
        results = compute_institution_results(conn, academic_year=academic_year)
    return integrity_store.save_results(conn, results)


def compute_rankings(
    conn: psycopg.Connection | None = None,
    academic_year: str = "2026-27",
) -> list[dict[str, Any]]:
    """Build InstitutionFeatures, call engine.anomaly and engine.scoring, persist results."""
    if conn is not None:
        results = compute_institution_results(conn, academic_year=academic_year)
        compute_and_save_integrity(conn, results=results, academic_year=academic_year)
        return integrity_store.latest_rankings(conn, academic_year=academic_year)
    with transaction() as c:
        results = compute_institution_results(c, academic_year=academic_year)
        compute_and_save_integrity(c, results=results, academic_year=academic_year)
        return integrity_store.latest_rankings(c, academic_year=academic_year)
