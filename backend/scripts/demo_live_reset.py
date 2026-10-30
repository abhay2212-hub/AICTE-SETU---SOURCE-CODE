# Owner: Dev B
"""Undo a live upload of deck/demo/shadow-late-batch.csv so it can be uploaded again.

Removes only what that file added at Shadow Institute of Technology: its batch (and any
correction batches of it), their rows, findings and admissions, the students it created,
and the review cases it opened (signal cases, Blind Match cases of its students, an
intake_overrun case it created). An intake_overrun case it only refreshed is put back to
the count without its rows. Nothing else is touched. Audit events are never deleted: one
demo_reset event is appended instead.

Run from backend/ (without --yes it only prints what it would remove):

    uv run python -m scripts.demo_live_reset --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import get_settings
from app.core.db import close_pool, transaction
from app.services import audit_store
from app.services.ingestion import file_sha256

LIVE_CSV = Path(__file__).resolve().parents[2] / "deck" / "demo" / "shadow-late-batch.csv"
SHADOW = "10000000-0000-4000-8000-000000000003"
ACTOR = "demo-script:demo_live_reset"


def find_batches(conn: psycopg.Connection, file_hash: str | None) -> list[str]:
    """Shadow batches of the live file (same hash or same file name) and their corrections."""
    rows = conn.execute(
        """
        with recursive live as (
          select id from public.batches
          where institution_id = %s and (file_hash = %s or file_name = %s)
          union
          select b.id from public.batches b join live on b.parent_batch_id = live.id
        )
        select id from live
        """,
        (SHADOW, file_hash, LIVE_CSV.name),
    ).fetchall()
    return [str(r["id"]) for r in rows]


def plan(conn: psycopg.Connection, batch_ids: list[str]) -> dict[str, Any]:
    """Everything the live batches added, by id."""
    students = [
        str(r["student_id"])
        for r in conn.execute(
            """
            select distinct a.student_id from public.admissions a
            where a.batch_id = any(%s::uuid[])
              and not exists (
                select 1 from public.admissions o
                where o.student_id = a.student_id
                  and (o.batch_id is null or o.batch_id <> all(%s::uuid[])))
            """,
            (batch_ids, batch_ids),
        ).fetchall()
    ]
    created = {
        case_id
        for r in conn.execute(
            "select commit_result from public.batches where id = any(%s::uuid[])", (batch_ids,)
        ).fetchall()
        for case_id in (r["commit_result"] or {}).get("review_cases_created", [])
    }
    cases = [
        str(r["id"])
        for r in conn.execute(
            """
            select id from public.review_cases
            where id = any(%s::uuid[])
               or (kind = 'signal' and evidence->>'batch_id' = any(%s))
               or (kind = 'blind_match'
                   and (evidence->>'student_a_id' = any(%s) or evidence->>'student_b_id' = any(%s)))
            """,
            (sorted(created), batch_ids, students, students),
        ).fetchall()
    ]
    refreshed = [
        r
        for r in conn.execute(
            "select id, evidence from public.review_cases"
            " where kind = 'intake_overrun' and evidence->>'batch_id' = any(%s)",
            (batch_ids,),
        ).fetchall()
        if str(r["id"]) not in cases
    ]
    admissions = conn.execute(
        "select count(*) as n from public.admissions where batch_id = any(%s::uuid[])",
        (batch_ids,),
    ).fetchone()["n"]
    return {
        "batches": batch_ids,
        "admissions": admissions,
        "students": students,
        "cases": cases,
        "overrun_cases": refreshed,
    }


def restore_overrun(conn: psycopg.Connection, case: dict[str, Any]) -> dict[str, Any]:
    """Recount the pool from the admissions that remain and point the case at the latest
    remaining batch with an admission in it. Run after the live admissions are deleted."""
    ev = case["evidence"]
    latest = conn.execute(
        """
        select count(*) as used,
               (array_agg(batch_id order by created_at desc))[1] as batch_id
        from public.admissions
        where active and programme_id = %s and academic_year = %s and pool = %s::public.seat_pool
        """,
        (ev["programme_id"], ev["academic_year"], ev["pool"]),
    ).fetchone()
    restored = {
        **ev,
        "used": latest["used"],
        "overrun_by": latest["used"] - ev["approved"],
        "batch_id": str(latest["batch_id"]) if latest["batch_id"] else None,
    }
    conn.execute(
        "update public.review_cases set evidence = %s, updated_at = now() where id = %s",
        (Jsonb(restored), case["id"]),
    )
    return {"case_id": str(case["id"]), "from": ev["overrun_by"], "to": restored["overrun_by"]}


def remove(conn: psycopg.Connection, found: dict[str, Any]) -> list[dict[str, Any]]:
    batches, students = found["batches"], found["students"]
    conn.execute("delete from public.review_cases where id = any(%s::uuid[])", (found["cases"],))
    # edit_requests and credentials of these admissions go with them (cascade / set null).
    conn.execute("delete from public.admissions where batch_id = any(%s::uuid[])", (batches,))
    # Children first; validation_issues and batch_rows cascade with their batch.
    conn.execute(
        "delete from public.batches where id = any(%s::uuid[]) and parent_batch_id is not null",
        (batches,),
    )
    conn.execute("delete from public.batches where id = any(%s::uuid[])", (batches,))
    # credentials, consents, access_log and telegram_links cascade with the student.
    conn.execute(
        "delete from public.credential_revocations where student_id = any(%s::uuid[])",
        (students,),
    )
    conn.execute("delete from public.students where id = any(%s::uuid[])", (students,))
    return [restore_overrun(conn, case) for case in found["overrun_cases"]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--yes", action="store_true", help="Remove the rows (required)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not get_settings().database_url:
        print("DATABASE_URL must be set in backend/.env")
        return 2
    try:
        return run(args.yes)
    finally:
        close_pool()


def run(confirmed: bool) -> int:
    file_hash = file_sha256(LIVE_CSV.read_bytes()) if LIVE_CSV.exists() else None
    with transaction() as conn:
        # Same lock as a Seat Ledger commit, so no Shadow commit runs while this does.
        conn.execute("select pg_advisory_xact_lock(hashtext('seat_ledger:' || %s))", (SHADOW,))
        batch_ids = find_batches(conn, file_hash)
        if not batch_ids:
            print(f"No Shadow batch of {LIVE_CSV.name}; nothing to reset.")
            return 0
        found = plan(conn, batch_ids)
        print(f"{LIVE_CSV.name} at Shadow Institute of Technology:")
        print(f"  batches            {len(found['batches'])}")
        print(f"  admissions         {found['admissions']}")
        print(f"  students created   {len(found['students'])}")
        print(f"  review cases       {len(found['cases'])}")
        print(f"  overrun cases      {len(found['overrun_cases'])} to recount")
        if not confirmed:
            print("Nothing changed. Add --yes to remove these.")
            return 2
        restored = remove(conn, found)
        audit_store.append_event(
            conn,
            ACTOR,
            "demo_reset",
            "batch",
            found["batches"][0] if len(found["batches"]) == 1 else None,
            {
                "file_name": LIVE_CSV.name,
                "batch_ids": found["batches"],
                "admissions_removed": found["admissions"],
                "students_removed": len(found["students"]),
                "review_cases_removed": found["cases"],
                "overrun_restored": restored,
            },
        )
    for item in restored:
        print(f"  overrun case {item['case_id']}  overrun_by {item['from']} -> {item['to']}")
    print("Removed. Audit events kept; one demo_reset event appended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
