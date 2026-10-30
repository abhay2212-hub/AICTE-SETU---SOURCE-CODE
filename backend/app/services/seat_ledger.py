# Owner: Dev B
"""Seat Ledger: approved intake per programme, academic year and pool, against active
admissions. Response fields keep the existing contract: admitted = used seats, available =
remaining seats."""

from __future__ import annotations

from typing import Any

import psycopg

from app.core.security import scoped_institution
from app.models.auth import User
from app.services.institutions import get_institution

POOLS = ("regular", "tfw", "fn_oci_pio", "nri")


def get_ledger(
    conn: psycopg.Connection, institution_id: str, academic_year: str, user: User
) -> dict[str, Any]:
    scoped_institution(user, institution_id)
    institution = get_institution(conn, institution_id, user)
    approved = conn.execute(
        """
        select distinct on (sp.programme_id, sp.pool)
               sp.programme_id, sp.pool::text as pool, sp.approved_seats, sp.rule_version
        from public.seat_pools sp
        join public.programmes p on p.id = sp.programme_id
        where p.institution_id = %s and sp.academic_year = %s
        order by sp.programme_id, sp.pool, sp.rule_version desc
        """,
        (institution_id, academic_year),
    ).fetchall()
    used = conn.execute(
        """
        select a.programme_id, a.pool::text as pool, count(*) as used
        from public.admissions a
        join public.programmes p on p.id = a.programme_id
        where a.active and p.institution_id = %s and a.academic_year = %s
        group by 1, 2
        """,
        (institution_id, academic_year),
    ).fetchall()
    seats = {(str(r["programme_id"]), r["pool"]): r for r in approved}
    counts = {(str(r["programme_id"]), r["pool"]): r["used"] for r in used}

    programmes = []
    for programme in institution["programmes"]:
        pid = programme["id"]
        pools = []
        for pool in POOLS:
            row = seats.get((pid, pool))
            if row is None and (pid, pool) not in counts:
                continue
            approved_seats = row["approved_seats"] if row else 0
            admitted = counts.get((pid, pool), 0)
            pools.append(
                {
                    "pool": pool,
                    "approved_seats": approved_seats,
                    "admitted": admitted,
                    "available": max(approved_seats - admitted, 0),
                    "overrun": max(admitted - approved_seats, 0),
                    "rule_version": row["rule_version"] if row else "none",
                }
            )
        if not pools:
            continue
        approved_total = sum(p["approved_seats"] for p in pools)
        admitted_total = sum(p["admitted"] for p in pools)
        programmes.append(
            {
                "programme_id": pid,
                "programme_code": programme["code"],
                "programme_name": programme["name"],
                "approved_total": approved_total,
                "admitted_total": admitted_total,
                "overrun": max(admitted_total - approved_total, 0),
                "pools": pools,
            }
        )
    return {
        "institution_id": institution_id,
        "academic_year": academic_year,
        "programmes": programmes,
    }
