# Owner: Dev B
"""Cross-institution Blind Match: the same person enrolled at two institutions.

Each committed student gets a Bloom-filter encoding of name, date of birth and guardian
(engine.blind_match.encoder.encode_identity, keyed with BLIND_MATCH_SECRET) and a DOB
block key. Students in the same block whose active admissions are at different
institutions are compared with dice; a score at or above MATCH_THRESHOLD opens one
blind_match review case per unordered student pair.

Unlike the upload hook (shared/engine-hooks.md section 4), pairs with two different valid
APAAR IDs ARE compared: across institutions that is exactly the fraud this looks for.
Pairs with the same APAAR or provisional ID are skipped (DUP_CROSS_INSTITUTION covers
them). Case evidence and broadcasts carry IDs and scores only: no names, dates of birth or
APAAR IDs.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from itertools import combinations
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from app.core.config import Settings, get_settings
from app.core.security import INSTITUTION_ROLES, scoped_institution
from app.models.auth import User
from app.services import audit_store
from app.services.batches import Event, case_created_event
from app.services.validation import BLOOM_BITS, dob_block_key

log = logging.getLogger(__name__)

ACTOR = "system:blind_match"
CASE_TITLE = "Possible same student at two institutions (Blind Match)"
HIDDEN = "hidden"
_warned_no_secret = False


# ---------------------------------------------------------------------------- encoding
def identity_fields(full_name: str, dob: date | str, guardian: str | None) -> dict[str, str]:
    """The fields the upload hook encodes: student_name, dob (ISO), guardian_name if any."""
    fields = {"student_name": full_name, "dob": dob if isinstance(dob, str) else dob.isoformat()}
    if guardian and guardian.strip():
        fields["guardian_name"] = guardian
    return fields


def encode(fields: dict[str, str], secret: str) -> bytes | None:
    """The 128-byte encoding, or None when the engine returns something off-contract."""
    from engine.blind_match.encoder import encode_identity

    bloom = encode_identity(fields, secret.encode(), bits=BLOOM_BITS)
    if not isinstance(bloom, bytes) or len(bloom) != BLOOM_BITS // 8:
        return None
    return bloom


def secret_or_warn(settings: Settings) -> str | None:
    """BLIND_MATCH_SECRET, or None after logging (once per process) that it is empty."""
    global _warned_no_secret
    if settings.blind_match_secret:
        return settings.blind_match_secret
    if not _warned_no_secret:
        log.warning("BLIND_MATCH_SECRET is empty; cross-institution Blind Match is skipped")
        _warned_no_secret = True
    return None


def store_encodings(conn: psycopg.Connection, student_ids: list[str], secret: str) -> int:
    """Compute and store bloom_identity and bloom_block for these students."""
    if not student_ids:
        return 0
    rows = conn.execute(
        "select id, full_name, dob, guardian_name from public.students where id = any(%s::uuid[])",
        (student_ids,),
    ).fetchall()
    updates = []
    for row in rows:
        bloom = encode(identity_fields(row["full_name"], row["dob"], row["guardian_name"]), secret)
        if bloom is not None:
            updates.append((bloom, dob_block_key(row["dob"], secret), row["id"]))
    if updates:
        with conn.cursor() as cur:
            cur.executemany(
                "update public.students set bloom_identity = %s, bloom_block = %s where id = %s",
                updates,
            )
    return len(updates)


def encode_new_students(conn: psycopg.Connection, student_ids: list[str]) -> None:
    """Commit hook: encode newly inserted students. Never raises (best effort)."""
    secret = secret_or_warn(get_settings())
    if not secret or not student_ids:
        return
    try:
        with conn.transaction():
            store_encodings(conn, student_ids, secret)
    except NotImplementedError:
        pass
    except Exception as exc:  # noqa: BLE001 - an engine bug must not break a commit
        log.warning("Blind Match encoding skipped for %d students: %s", len(student_ids), exc)


# ---------------------------------------------------------------------------- pure matching
@dataclass(frozen=True)
class Placement:
    """One active admission."""

    institution_id: str
    programme: str
    academic_year: str
    admitted_at: datetime


@dataclass(frozen=True)
class Candidate:
    student_id: str
    block: str
    bloom: bytes
    apaar_id: str | None
    provisional_id: str | None
    has_guardian: bool
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class Match:
    a: Candidate
    b: Candidate
    place_a: Placement
    place_b: Placement
    dice: float

    @property
    def pair_key(self) -> str:
        return pair_key(self.a.student_id, self.b.student_id)


def pair_key(a: str, b: str) -> str:
    return f"{min(a, b)}:{max(a, b)}"


def cross_placements(a: Candidate, b: Candidate) -> tuple[Placement, Placement] | None:
    """The most recent pair of active admissions at two different institutions, if any."""
    pairs = [
        (pa, pb)
        for pa in a.placements
        for pb in b.placements
        if pa.institution_id != pb.institution_id
    ]
    if not pairs:
        return None
    return max(pairs, key=lambda p: max(p[0].admitted_at, p[1].admitted_at))


def same_identifier(a: Candidate, b: Candidate) -> bool:
    return bool(
        (a.apaar_id and a.apaar_id == b.apaar_id)
        or (a.provisional_id and a.provisional_id == b.provisional_id)
    )


def find_matches(
    candidates: list[Candidate],
    threshold: float,
    targets: set[str] | None = None,
    max_block: int = 200,
) -> list[Match]:
    """Pairs in the same block, at different institutions, scoring at or above threshold.

    With ``targets`` only pairs involving at least one target student are compared. Each
    unordered pair appears once; ``a`` is the student with the smaller id.
    """
    from engine.blind_match.encoder import dice

    blocks: dict[str, list[Candidate]] = defaultdict(list)
    for c in sorted(candidates, key=lambda c: c.student_id):
        blocks[c.block].append(c)
    out = []
    for members in blocks.values():
        if len(members) > max_block:
            log.warning("Blind Match block of %d students truncated to %d", len(members), max_block)
            members = members[:max_block]
        for a, b in combinations(members, 2):
            if targets is not None and a.student_id not in targets and b.student_id not in targets:
                continue
            if a.student_id == b.student_id or same_identifier(a, b):
                continue
            places = cross_placements(a, b)
            if places is None:
                continue
            score = float(dice(a.bloom, b.bloom))
            if score >= threshold:
                out.append(Match(a, b, places[0], places[1], round(score, 3)))
    return out


def evidence(match: Match) -> dict[str, Any]:
    """IDs, programmes, years and the score; never names, dates of birth or APAAR IDs."""
    matched_on = ["name", "dob"] + (
        ["guardian"] if match.a.has_guardian and match.b.has_guardian else []
    )
    return {
        "pair_key": match.pair_key,
        "student_a_id": match.a.student_id,
        "student_b_id": match.b.student_id,
        "institution_a_id": match.place_a.institution_id,
        "institution_b_id": match.place_b.institution_id,
        "programme_a": match.place_a.programme,
        "academic_year_a": match.place_a.academic_year,
        "programme_b": match.place_b.programme,
        "academic_year_b": match.place_b.academic_year,
        "dice": match.dice,
        "matched_on": matched_on,
    }


# ---------------------------------------------------------------------------- database
_CANDIDATES = """
    select s.id, s.bloom_block, s.bloom_identity, s.apaar_id, s.provisional_id,
           s.guardian_name, p.institution_id, p.code as programme, a.academic_year,
           a.created_at as admitted_at
    from public.students s
    join public.admissions a on a.student_id = s.id and a.active
    join public.programmes p on p.id = a.programme_id
    where s.bloom_identity is not null and s.bloom_block is not null
"""


def _candidates(rows: list[dict[str, Any]]) -> list[Candidate]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["id"])].append(row)
    out = []
    for student_id, group in grouped.items():
        first = group[0]
        out.append(
            Candidate(
                student_id=student_id,
                block=first["bloom_block"],
                bloom=bytes(first["bloom_identity"]),
                apaar_id=first["apaar_id"],
                provisional_id=first["provisional_id"],
                has_guardian=bool((first["guardian_name"] or "").strip()),
                placements=tuple(
                    Placement(
                        str(r["institution_id"]),
                        r["programme"],
                        r["academic_year"],
                        r["admitted_at"],
                    )
                    for r in group
                ),
            )
        )
    return out


def _open_cases(conn: psycopg.Connection, matches: list[Match]) -> tuple[list[str], list[Event]]:
    """Insert one case per new pair; pairs that already have a case are left alone."""
    created: list[str] = []
    events: list[Event] = []
    for match in matches:
        # The case belongs to the institution that admitted the student most recently.
        newer = max((match.place_a, match.place_b), key=lambda p: p.admitted_at)
        case = conn.execute(
            """
            insert into public.review_cases (kind, institution_id, title, evidence)
            values ('blind_match', %s, %s, %s)
            on conflict ((evidence->>'pair_key')) where kind = 'blind_match' do nothing
            returning id, kind, institution_id, status::text as status, created_at
            """,
            (newer.institution_id, CASE_TITLE, Jsonb(evidence(match))),
        ).fetchone()
        if case is None:
            continue
        created.append(str(case["id"]))
        audit_store.append_event(
            conn,
            ACTOR,
            "review_case.created",
            "review_case",
            case["id"],
            {"kind": "blind_match", "pair_key": match.pair_key, "dice": match.dice},
        )
        events.append(case_created_event(case))
    return created, events


def match_students(
    conn: psycopg.Connection, student_ids: list[str], settings: Settings | None = None
) -> tuple[list[str], list[Event]]:
    """Compare these students with every candidate in their DOB blocks; open new cases."""
    settings = settings or get_settings()
    if not student_ids or not secret_or_warn(settings):
        return [], []
    blocks = [
        r["bloom_block"]
        for r in conn.execute(
            "select distinct bloom_block from public.students"
            " where id = any(%s::uuid[]) and bloom_block is not null",
            (student_ids,),
        ).fetchall()
    ]
    if not blocks:
        return [], []
    rows = conn.execute(f"{_CANDIDATES} and s.bloom_block = any(%s)", (blocks,)).fetchall()
    matches = find_matches(
        _candidates(rows),
        settings.match_threshold,
        targets={str(s) for s in student_ids},
        max_block=settings.blind_match_max_block,
    )
    return _open_cases(conn, matches)


def match_batch(conn: psycopg.Connection, batch_id: str) -> tuple[list[str], list[Event]]:
    """match_students for every student with an active admission from this batch."""
    ids = [
        str(r["student_id"])
        for r in conn.execute(
            "select distinct student_id from public.admissions where batch_id = %s and active",
            (batch_id,),
        ).fetchall()
    ]
    return match_students(conn, ids)


def match_after_commit(batch_id: str) -> None:
    """Run after a successful commit, in its own transaction. Never raises."""
    from app.core.db import transaction
    from app.services import realtime

    try:
        with transaction() as conn:
            _, events = match_batch(conn, batch_id)
    except Exception as exc:  # noqa: BLE001 - matching must never fail a commit
        log.warning("Blind Match after commit of batch %s failed: %s", batch_id, exc)
        return
    realtime.publish(events)


def scan_all(conn: psycopg.Connection, settings: Settings | None = None) -> dict[str, Any]:
    """Full rescan: encode students that have no encoding yet, then compare every block.

    Idempotent: pairs that already have a case are skipped by the unique pair rule.
    """
    settings = settings or get_settings()
    secret = secret_or_warn(settings)
    if not secret:
        return {"students_encoded": 0, "candidates": 0, "matches": 0, "cases_created": []}
    missing = [
        str(r["id"])
        for r in conn.execute(
            "select distinct s.id from public.students s"
            " join public.admissions a on a.student_id = s.id and a.active"
            " where s.bloom_identity is null or s.bloom_block is null"
        ).fetchall()
    ]
    encoded = store_encodings(conn, missing, secret)
    candidates = _candidates(conn.execute(_CANDIDATES).fetchall())
    matches = find_matches(
        candidates, settings.match_threshold, max_block=settings.blind_match_max_block
    )
    created, events = _open_cases(conn, matches)
    return {
        "students_encoded": encoded,
        "candidates": len(candidates),
        "matches": len(matches),
        "cases_created": created,
        "events": events,
    }


# ---------------------------------------------------------------------------- reading
def identity_hint(full_name: str | None, dob: date | None) -> str | None:
    """Initials and birth year, e.g. 'A. S., 2008'. Only for aicte_admin and auditor."""
    if not full_name or dob is None:
        return None
    initials = " ".join(f"{part[0].upper()}." for part in full_name.split() if part)
    return f"{initials}, {dob.year}"


def case_view(row: dict[str, Any], user: User) -> dict[str, Any]:
    """BlindMatchCase for this user. Institution users see the other side hidden."""
    ev = row["evidence"]
    out: dict[str, Any] = {
        "id": str(row["id"]),
        "record_a": ev["student_a_id"],
        "record_b": ev["student_b_id"],
        "institution_a_id": ev["institution_a_id"],
        "institution_b_id": ev["institution_b_id"],
        "institution_a_name": row.get("institution_a_name"),
        "institution_b_name": row.get("institution_b_name"),
        "programme_a": ev.get("programme_a"),
        "programme_b": ev.get("programme_b"),
        "academic_year_a": ev.get("academic_year_a"),
        "academic_year_b": ev.get("academic_year_b"),
        "dice": float(ev["dice"]),
        "fields_compared": list(ev.get("matched_on") or []),
        "status": row["status"],
        "review_case_id": str(row["id"]),
        "created_at": row.get("created_at"),
        "identity_hint_a": None,
        "identity_hint_b": None,
    }
    if user.role in INSTITUTION_ROLES:
        for side in ("a", "b"):
            if out[f"institution_{side}_id"] != user.institution_id:
                out.update(
                    {
                        f"record_{side}": HIDDEN,
                        f"institution_{side}_id": HIDDEN,
                        f"institution_{side}_name": None,
                    }
                )
    else:
        out["identity_hint_a"] = identity_hint(row.get("name_a"), row.get("dob_a"))
        out["identity_hint_b"] = identity_hint(row.get("name_b"), row.get("dob_b"))
    return out


def list_cases(conn: psycopg.Connection, user: User) -> list[dict[str, Any]]:
    """blind_match cases, newest first. Institution users see only cases involving them."""
    institution = scoped_institution(user)
    rows = conn.execute(
        """
        select rc.id, rc.status::text as status, rc.evidence, rc.created_at,
               ia.name as institution_a_name, ib.name as institution_b_name,
               sa.full_name as name_a, sa.dob as dob_a, sb.full_name as name_b, sb.dob as dob_b
        from public.review_cases rc
        left join public.institutions ia on ia.id::text = rc.evidence->>'institution_a_id'
        left join public.institutions ib on ib.id::text = rc.evidence->>'institution_b_id'
        left join public.students sa on sa.id::text = rc.evidence->>'student_a_id'
        left join public.students sb on sb.id::text = rc.evidence->>'student_b_id'
        where rc.kind = 'blind_match' and rc.evidence ? 'pair_key'
          and (%(inst)s::text is null
               or rc.evidence->>'institution_a_id' = %(inst)s
               or rc.evidence->>'institution_b_id' = %(inst)s)
        order by rc.created_at desc, rc.id
        """,
        {"inst": institution},
    ).fetchall()
    return [case_view(r, user) for r in rows]


def fixture_cases(cases: list[dict[str, Any]], user: User) -> list[dict[str, Any]]:
    """Fixture mode: the same institution scoping applied to the fixture cases."""
    if user.role not in INSTITUTION_ROLES:
        return cases
    institution = scoped_institution(user)
    out = []
    for case in cases:
        if institution not in (case["institution_a_id"], case["institution_b_id"]):
            continue
        for side in ("a", "b"):
            if case[f"institution_{side}_id"] != institution:
                case = {**case, f"record_{side}": HIDDEN, f"institution_{side}_id": HIDDEN}
        out.append(case)
    return out
