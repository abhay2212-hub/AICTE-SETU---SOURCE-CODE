# Owner: Dev B
"""The signed-in student's records, consent ledger and access log (shared/credentials.md).

Every function takes the resolved student id; nothing here reads another student's rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from fastapi import HTTPException, status

from app.models.auth import User
from app.services import audit_store
from app.services.admissions import _SELECT, _admission
from app.services.batches import as_uuid
from app.services.validation import mask_apaar

# Fixture student that role=student maps to in fixture mode.
FIXTURE_STUDENT = "40000000-0000-4000-8000-000000000001"
APAAR_SHARING = "apaar_sharing"
APAAR_VERIFIER = ("apaar-simulated", "APAAR (SIMULATED)")
ACCESS_LOG_LIMIT = 200


def fixture_student_id(user: User, demo_student: str | None) -> str:
    if user.demo:
        return demo_student or FIXTURE_STUDENT
    return _linked(user)


def _linked(user: User) -> str:
    if not user.student_id or as_uuid(user.student_id) is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This account is not linked to a student record"
        )
    return str(as_uuid(user.student_id))


def resolve_student_id(conn: psycopg.Connection, user: User, demo_student: str | None) -> str:
    """The student this request acts for.

    MOCK_MODE: X-Demo-Student when sent, else the student marked is_demo. Otherwise the
    student_id in the token's app_metadata.
    """
    if not user.demo:
        student_id = _linked(user)
        row = conn.execute("select id from public.students where id = %s", (student_id,))
    elif demo_student:
        if as_uuid(demo_student) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "X-Demo-Student is not a student id")
        row = conn.execute("select id from public.students where id = %s", (demo_student,))
    else:
        row = conn.execute(
            "select id from public.students where is_demo order by created_at, id limit 1"
        )
    found = row.fetchone()
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {"code": "DEMO_STUDENT_NOT_FOUND", "message": "No student record for this user"},
        )
    return str(found["id"])


# ---------------------------------------------------------------------------- records
def records(conn: psycopg.Connection, student_id: str) -> dict[str, Any]:
    student = conn.execute(
        """
        select s.id, s.full_name, s.apaar_id, s.provisional_id, s.opted_out, s.dob,
               exists (select 1 from public.telegram_links t
                       where t.student_id = s.id and t.linked_at is not null) as telegram_linked
        from public.students s where s.id = %s
        """,
        (student_id,),
    ).fetchone()
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Student '{student_id}' not found")
    admissions = conn.execute(
        f"{_SELECT} where a.student_id = %s order by a.created_at desc, a.id", (student_id,)
    ).fetchall()
    masked = mask_apaar(student["apaar_id"])
    profile = {
        **student,
        "id": str(student["id"]),
        "apaar_id": masked,
        "apaar_id_masked": masked,
    }
    return {"student": profile, "admissions": [_admission(a) for a in admissions]}


def own_admission(conn: psycopg.Connection, student_id: str, admission_id: str) -> None:
    """404 unless the admission belongs to the student (never reveals other students')."""
    row = (
        conn.execute(
            "select 1 from public.admissions where id = %s and student_id = %s",
            (admission_id, student_id),
        ).fetchone()
        if as_uuid(admission_id)
        else None
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            {"code": "ADMISSION_NOT_FOUND", "message": f"Admission '{admission_id}' not found"},
        )


# ---------------------------------------------------------------------------- consents
_CONSENT_COLUMNS = (
    "id, verifier_id, verifier_name, purpose, fields, granted_at, expires_at, revoked_at"
)


def _consent(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "id": str(row["id"])}


def consents(conn: psycopg.Connection, student_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"select {_CONSENT_COLUMNS} from public.consents where student_id = %s"
        " order by granted_at desc, id",
        (student_id,),
    ).fetchall()
    return [_consent(r) for r in rows]


def change_consent(
    conn: psycopg.Connection, student_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Grant (or renew) or withdraw one consent; apaar_sharing is the APAAR opt-in."""
    purpose = body["purpose"].strip()
    if purpose == APAAR_SHARING:
        verifier_id, verifier_name = APAAR_VERIFIER
    else:
        verifier_id = body["verifier_id"].strip()
        verifier_name = (body.get("verifier_name") or "").strip() or verifier_id
    active = conn.execute(
        f"""
        select {_CONSENT_COLUMNS} from public.consents
        where student_id = %s and verifier_id = %s and purpose = %s
          and revoked_at is null and expires_at > now()
        order by granted_at desc limit 1 for update
        """,
        (student_id, verifier_id, purpose),
    ).fetchone()
    expires = datetime.now(UTC) + timedelta(days=body["expires_in_days"])
    if body.get("action") in (None, "grant"):
        if active:
            row = conn.execute(
                f"""
                update public.consents set fields = %s, expires_at = %s, verifier_name = %s
                where id = %s returning {_CONSENT_COLUMNS}
                """,
                (body["fields"], expires, verifier_name, active["id"]),
            ).fetchone()
        else:
            row = conn.execute(
                f"""
                insert into public.consents
                  (student_id, verifier_id, verifier_name, purpose, fields, expires_at)
                values (%s, %s, %s, %s, %s, %s) returning {_CONSENT_COLUMNS}
                """,
                (student_id, verifier_id, verifier_name, purpose, body["fields"], expires),
            ).fetchone()
        action = "consent.granted"
    elif active:
        row = conn.execute(
            f"update public.consents set revoked_at = now() where id = %s"
            f" returning {_CONSENT_COLUMNS}",
            (active["id"],),
        ).fetchone()
        action = "consent.withdrawn"
    elif purpose == APAAR_SHARING:
        # The opt-out is recorded even when no opt-in was ever given.
        row = conn.execute(
            f"""
            insert into public.consents
              (student_id, verifier_id, verifier_name, purpose, fields, expires_at, revoked_at)
            values (%s, %s, %s, %s, %s, %s, now()) returning {_CONSENT_COLUMNS}
            """,
            (student_id, verifier_id, verifier_name, purpose, ["apaar_id"], expires),
        ).fetchone()
        action = "consent.withdrawn"
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No active consent to withdraw")
    audit_store.append_event(
        conn,
        f"student:{student_id}",
        action,
        "consent",
        row["id"],
        {"verifier_id": verifier_id, "purpose": purpose, "fields": list(row["fields"])},
    )
    return _consent(row)


# ---------------------------------------------------------------------------- access log
def access_log(conn: psycopg.Connection, student_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select id, accessor, accessor_role::text as accessor_role, purpose, fields, consent_id,
               accessed_at
        from public.access_log where student_id = %s
        order by accessed_at desc, id limit %s
        """,
        (student_id, ACCESS_LOG_LIMIT),
    ).fetchall()
    return [
        {
            **r,
            "id": str(r["id"]),
            "consent_id": str(r["consent_id"]) if r["consent_id"] else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------- fixtures
def fixture_consent(body: dict[str, Any], current: list[dict[str, Any]]) -> dict[str, Any]:
    """Fixture-mode answer to POST /students/me/consents (nothing is stored)."""
    now = datetime.now(UTC)
    purpose = body["purpose"].strip()
    verifier_id, name = (
        APAAR_VERIFIER
        if purpose == APAAR_SHARING
        else (body["verifier_id"], body.get("verifier_name") or body["verifier_id"])
    )
    match = next(
        (c for c in current if c["verifier_id"] == verifier_id and c["purpose"] == purpose),
        None,
    )
    consent = dict(match or current[0])
    consent.update(verifier_id=verifier_id, verifier_name=name, purpose=purpose)
    if body["action"] == "withdraw":
        consent["revoked_at"] = now.isoformat()
        return consent
    consent.update(
        fields=body["fields"],
        granted_at=now.isoformat(),
        expires_at=(now + timedelta(days=body["expires_in_days"])).isoformat(),
        revoked_at=None,
    )
    return consent
