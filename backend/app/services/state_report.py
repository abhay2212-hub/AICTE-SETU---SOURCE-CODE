# Owner: Dev B
"""State-by-state aggregates for the AICTE map (F27): institutions, active admissions against
approved seats, programmes over intake, open review cases and Integrity Scores.

Aggregates only: nothing here reads or returns student-level data.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import psycopg

from app.services import integrity_store


def build(
    institutions: list[dict[str, Any]],
    programmes: list[dict[str, Any]],
    open_cases: dict[str, int],
    scores: dict[str, float],
    academic_year: str,
) -> dict[str, Any]:
    """``programmes``: one row per programme with ``institution_id``, ``approved`` (latest seat
    rule per pool, summed) and ``admitted`` (active admissions). States with no institution
    are left out; institutions are listed lowest Integrity Score first (unscored last)."""
    by_institution: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for programme in programmes:
        by_institution[str(programme["institution_id"])].append(programme)

    states: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for institution in institutions:
        states[institution["state"]].append(institution)

    rows = []
    for state in sorted(states):
        listed, admitted, approved, overrun_programmes, cases = [], 0, 0, 0, 0
        state_scores = []
        for institution in states[state]:
            iid = str(institution["id"])
            own = by_institution.get(iid, [])
            over = sum(1 for p in own if p["admitted"] > p["approved"])
            admitted += sum(int(p["admitted"]) for p in own)
            approved += sum(int(p["approved"]) for p in own)
            overrun_programmes += over
            open_count = int(open_cases.get(iid, 0))
            cases += open_count
            score = scores.get(iid)
            if score is not None:
                state_scores.append(float(score))
            listed.append(
                {
                    "institution_id": iid,
                    "name": institution["name"],
                    "aicte_code": institution["aicte_code"],
                    "integrity_score": None if score is None else round(float(score), 1),
                    "open_review_cases": open_count,
                    "overrun": over > 0,
                }
            )
        listed.sort(
            key=lambda i: (i["integrity_score"] is None, i["integrity_score"] or 0, i["name"])
        )
        rows.append(
            {
                "state": state,
                "institutions": len(listed),
                "active_admissions": admitted,
                "approved_seats": approved,
                "utilisation": round(admitted / approved, 4) if approved else None,
                "overrun_programmes": overrun_programmes,
                "open_review_cases": cases,
                "avg_integrity_score": (
                    round(sum(state_scores) / len(state_scores), 1) if state_scores else None
                ),
                "institutions_list": listed,
            }
        )
    totals = {
        key: sum(row[key] for row in rows)
        for key in (
            "institutions",
            "active_admissions",
            "approved_seats",
            "overrun_programmes",
            "open_review_cases",
        )
    }
    return {"academic_year": academic_year, "totals": {**totals, "states": len(rows)}, "rows": rows}


def from_db(conn: psycopg.Connection, academic_year: str) -> dict[str, Any]:
    institutions = conn.execute(
        "select id::text as id, name, aicte_code, state from public.institutions"
    ).fetchall()
    # Approved seats use the latest rule version per (programme, pool), as in the Seat Ledger.
    programmes = conn.execute(
        """
        with seats as (
          select distinct on (sp.programme_id, sp.pool) sp.programme_id, sp.approved_seats
          from public.seat_pools sp
          where sp.academic_year = %s
          order by sp.programme_id, sp.pool, sp.rule_version desc
        ), approved as (
          select programme_id, sum(approved_seats)::int as seats from seats group by programme_id
        ), admitted as (
          select a.programme_id, count(*)::int as n from public.admissions a
          where a.active and a.academic_year = %s
          group by a.programme_id
        )
        select p.institution_id::text as institution_id,
               coalesce(ap.seats, 0) as approved, coalesce(ad.n, 0) as admitted
        from public.programmes p
        left join approved ap on ap.programme_id = p.id
        left join admitted ad on ad.programme_id = p.id
        where ap.programme_id is not null or ad.programme_id is not null
        """,
        (academic_year, academic_year),
    ).fetchall()
    cases = conn.execute(
        """
        select institution_id::text as institution_id, count(*)::int as n
        from public.review_cases
        where status = 'open'
          and (evidence->>'academic_year' = %s or evidence->>'academic_year' is null)
        group by institution_id
        """,
        (academic_year,),
    ).fetchall()
    scores = {
        r["institution_id"]: r["integrity_score"]
        for r in integrity_store.latest_rankings(conn, academic_year)
    }
    return build(
        institutions,
        programmes,
        {r["institution_id"]: r["n"] for r in cases},
        scores,
        academic_year,
    )


def from_fixtures(
    institutions: list[dict[str, Any]],
    seat_ledger: dict[str, Any],
    review_cases: list[dict[str, Any]],
    academic_year: str,
) -> dict[str, Any]:
    """The same report from the JSON fixtures (used to generate mocks/state_report.json)."""
    programmes = [
        {
            "institution_id": ledger["institution_id"],
            "approved": p["approved_total"],
            "admitted": p["admitted_total"],
        }
        for ledger in seat_ledger.values()
        if ledger["academic_year"] == academic_year
        for p in ledger["programmes"]
    ]
    open_cases: dict[str, int] = defaultdict(int)
    for case in review_cases:
        if case["status"] == "open":
            open_cases[case["institution_id"]] += 1
    scores = {
        i["id"]: i["integrity_score"] for i in institutions if i.get("integrity_score") is not None
    }
    return build(institutions, programmes, open_cases, scores, academic_year)
