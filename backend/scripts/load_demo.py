# Owner: Dev B
"""Load the demo dataset through the real services: upload, validation, Seat Ledger commit.

Every batch goes through app.services.batches exactly as the API would run it, so batches,
findings, review cases and the audit chain are all genuine. Synthetic data only.

Run from backend/:

    uv run python -m scripts.load_demo --reset --yes
    uv run python -m scripts.load_demo --institutions 25 --students 5000 --seed 42
    uv run python -m scripts.load_demo --source ../datagen/out

See scripts/README.md for the Shadow Institute story the loader scripts.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg

from app.core.config import get_settings
from app.core.db import close_pool, transaction
from app.models.auth import User
from app.services import audit_store, blind_match, realtime
from app.services import batches as batch_service
from app.services import submission_windows as windows
from app.services.ingestion import TEMPLATE_COLUMNS

DATAGEN = Path(__file__).resolve().parents[2] / "datagen"
YEAR = "2026-27"
ORIGIN = "load_demo"

MEGHDOOT = "10000000-0000-4000-8000-000000000001"
NARMADA = "10000000-0000-4000-8000-000000000002"
SHADOW = "10000000-0000-4000-8000-000000000003"
SEED_INSTITUTIONS = {
    MEGHDOOT: ("1-9999001", "Maharashtra"),
    NARMADA: ("1-9999002", "Madhya Pradesh"),
    SHADOW: ("1-9999003", "Uttar Pradesh"),
}

# Deleted by --reset, children first. Institutions, programmes and seat pools from
# supabase/seed.sql stay; institutions this script created (origin = load_demo) go last.
RESET_TABLES = (
    "credentials",
    "integrity_scores",
    "access_log",
    "consents",
    "telegram_links",
    "credential_revocations",
    "edit_requests",
    "review_cases",
    "validation_issues",
    "batch_rows",
    "admissions",
    "batches",
    "students",
    "audit_events",
)

PROGRAMME_NAMES = {
    "UG-CSE": "B.Tech Computer Science and Engineering",
    "UG-ECE": "B.Tech Electronics and Communication Engineering",
    "UG-ME": "B.Tech Mechanical Engineering",
    "UG-CE": "B.Tech Civil Engineering",
    "UG-EE": "B.Tech Electrical Engineering",
    "UG-IT": "B.Tech Information Technology",
    "UG-AIDS": "B.Tech Artificial Intelligence and Data Science",
    "PG-MBA": "Master of Business Administration",
    "PG-MCA": "Master of Computer Applications",
}

FIRST_MALE = (
    "Aarav Aditya Akash Aman Ankit Arjun Aryan Ayaan Dev Dhruv Harsh Ishaan Kabir Karan"
    " Krishna Kunal Manav Mohit Nikhil Pranav Rahul Rajat Rohan Sahil Sai Sameer Shaurya"
    " Siddharth Tanmay Utkarsh Varun Vedant Vihaan Vivek Yash"
).split()
FIRST_FEMALE = (
    "Aadhya Ananya Anika Anjali Avni Diya Divya Isha Ishita Jiya Kavya Khushi Kriti Meera"
    " Myra Neha Nisha Pari Pooja Prisha Riya Saanvi Sakshi Sanya Shreya Simran Sneha Tanvi"
    " Tara Trisha Vanya Zara"
).split()
LAST = (
    "Agarwal Bansal Bhatt Chauhan Chaudhary Desai Dubey Gupta Iyer Jain Joshi Kapoor Khan"
    " Kulkarni Kumar Mehta Mishra Nair Pandey Patel Patil Rao Reddy Saxena Shah Sharma"
    " Shukla Singh Sinha Srivastava Tiwari Trivedi Verma Yadav"
).split()
EXAMS = {
    "Maharashtra": ("JEE Main", "MHT CET"),
    "Madhya Pradesh": ("JEE Main",),
    "Uttar Pradesh": ("JEE Main", "UPTAC"),
}
FOREIGN = ("NP", "AE", "US", "GB", "SG")


# ---------------------------------------------------------------------------- scripted rows
class Scripted:
    """Deterministic, believable rows for the three seed institutions."""

    def __init__(self, seed: int, taken_apaars: set[str]) -> None:
        self.rng = random.Random(seed)
        self.taken = set(taken_apaars)
        self.serial = 0

    def apaar(self, block: int) -> str:
        # 9999 + 2-digit block + 6-digit serial, skipping any APAAR the source data uses.
        while True:
            self.serial += 1
            value = f"9999{block:02d}{self.serial:06d}"
            if value not in self.taken:
                self.taken.add(value)
                return value

    def row(self, code: str, state: str, programme: str, pool: str, block: int) -> dict[str, str]:
        rng, n = self.rng, self.serial + 1
        gender = rng.choices(["male", "female"], [0.6, 0.4])[0]
        first = rng.choice(FIRST_FEMALE if gender == "female" else FIRST_MALE)
        last = rng.choice(LAST)
        foreign = pool == "fn_oci_pio"
        oci = foreign and rng.random() < 0.5
        return {
            "institution_aicte_code": code,
            "programme_code": programme,
            "academic_year": YEAR,
            "student_name": f"{first} {last}",
            "dob": (date(2007, 6, 1) + timedelta(days=rng.randint(0, 720))).isoformat(),
            "gender": gender,
            "category": rng.choices(["general", "ews", "obc", "sc", "st"], [40, 8, 30, 15, 7])[0],
            "pwd": "true" if rng.random() < 0.02 else "false",
            "apaar_id": self.apaar(block),
            "apaar_opt_out": "false",
            "provisional_id": "",
            "nationality": rng.choice(FOREIGN) if foreign else "IN",
            "oci_status": str(oci).lower(),
            "fn_status": str(foreign and not oci).lower(),
            "nri_category": str(pool == "nri").lower(),
            "seat_pool": pool,
            "admission_mode": "management" if pool == "nri" else rng.choice(["cap"] * 6 + ["spot"]),
            "admission_date": (date(2026, 7, 20) + timedelta(days=rng.randint(0, 57))).isoformat(),
            "qualifying_exam": rng.choice(EXAMS.get(state, ("JEE Main",))),
            "qualifying_exam_pct": f"{rng.uniform(58, 98):.2f}",
            "domicile_state": state,
            "contact_phone": f"+9196{block:02d}{n:06d}",
            "contact_email": f"{first}.{last}.{block}{n:05d}@example.com".lower(),
            "guardian_name": f"{rng.choice(FIRST_MALE)} {last}",
        }

    def clean(
        self, institution: str, plan: dict[tuple[str, str], int], block: int
    ) -> list[dict[str, str]]:
        code, state = SEED_INSTITUTIONS[institution]
        rows = [
            self.row(code, state, programme, pool, block)
            for (programme, pool), count in plan.items()
            for _ in range(count)
        ]
        self.rng.shuffle(rows)
        return rows


MEGHDOOT_PLAN = {
    ("UG-CSE", "regular"): 98,
    ("UG-CSE", "tfw"): 6,
    ("UG-CSE", "fn_oci_pio"): 4,
    ("UG-CSE", "nri"): 5,
    ("UG-ME", "regular"): 46,
    ("UG-ME", "tfw"): 3,
    ("UG-ME", "fn_oci_pio"): 2,
    ("UG-ME", "nri"): 3,
}
NARMADA_PLAN = {
    ("UG-CSE", "regular"): 96,
    ("UG-CSE", "tfw"): 5,
    ("UG-CSE", "fn_oci_pio"): 3,
    ("UG-CSE", "nri"): 4,
    ("UG-ECE", "regular"): 47,
    ("UG-ECE", "tfw"): 3,
    ("UG-ECE", "fn_oci_pio"): 2,
    ("UG-ECE", "nri"): 3,
}

# The Shadow Institute of Technology CSE 2026-27 batch. Seed seats for UG-CSE are 51 regular
# + 3 tfw + 3 fn_oci_pio + 3 nri = 60. 71 rows commit (62 regular, 3 per other pool), so the
# regular pool runs 11 over and the programme is 71 against 60. One regular row is a
# misspelled copy of a Narmada CSE student with a different APAAR: one Blind Match case.
SHADOW_STORY = {
    "admitted": 71,
    "approved": 60,
    "overrun_by": 11,
    "contact_cluster": 6,
    "after_cutoff": 3,
    "cross_institution": 2,
    "opted_out": 2,
    "rejected": 4,
    "blind_match_with_narmada": 1,
}
SHARED_PHONE = "+919755500011"
SHARED_EMAIL = "admissions.desk.shadow@example.com"
AFTER_CUTOFF_DATES = ("2026-10-03", "2026-10-08", "2026-10-14")


def misspell(name: str) -> str:
    """A one-letter typo: the last letter typed twice ("Aadhya Patel" -> "Aadhya Patell")."""
    return name + name[-1]


def typo_copy(row: dict[str, str], source: dict[str, str]) -> dict[str, str]:
    """``row`` as the same person as ``source``: misspelled name, same DOB and guardian.
    The APAAR ID and contacts stay ``row``'s own, so only Blind Match can link the two."""
    return {
        **row,
        **{k: source[k] for k in ("dob", "gender", "category", "guardian_name")},
        "student_name": misspell(source["student_name"]),
    }


def shadow_rows(
    gen: Scripted, narmada_twins: list[dict[str, str]], narmada_typo: dict[str, str]
) -> list[dict[str, str]]:
    """75 rows: 71 that commit and 4 with one hard error each."""
    code, state = SEED_INSTITUTIONS[SHADOW]
    block = 3

    def regular() -> dict[str, str]:
        return gen.row(code, state, "UG-CSE", "regular", block)

    plain = [regular() for _ in range(62 - 6 - 3 - 2 - 2 - 1)]
    cluster = [regular() for _ in range(6)]
    for row in cluster:
        row.update(contact_phone=SHARED_PHONE, contact_email=SHARED_EMAIL)
    late = [regular() for _ in AFTER_CUTOFF_DATES]
    for row, day in zip(late, AFTER_CUTOFF_DATES, strict=True):
        row.update(admission_date=day, admission_mode="spot")
    twins = []
    for source in narmada_twins:
        row = regular()
        for key in (
            "student_name",
            "dob",
            "gender",
            "category",
            "apaar_id",
            "guardian_name",
            "contact_phone",
            "contact_email",
        ):
            row[key] = source[key]
        twins.append(row)
    typo = [typo_copy(regular(), narmada_typo)]
    opted = [regular() for _ in range(2)]
    for n, row in enumerate(opted, start=1):
        row.update(apaar_id="", apaar_opt_out="true", provisional_id=f"PROV-{code}-{n:04d}")
    others = [
        gen.row(code, state, "UG-CSE", pool, block)
        for pool in ("tfw", "fn_oci_pio", "nri")
        for _ in range(3)
    ]
    valid = plain + cluster + late + twins + typo + opted + others
    gen.rng.shuffle(valid)

    broken = [regular() for _ in range(4)]
    broken[0]["student_name"] = ""  # REQUIRED_FIELD_MISSING
    broken[1]["apaar_id"] = broken[1]["apaar_id"][:11]  # APAAR_FORMAT
    broken[2]["programme_code"] = "UG-AERO"  # PROGRAMME_UNKNOWN
    broken[3]["admission_date"] = "2026-02-30"  # DATE_INVALID
    rows = list(valid)
    for position, row in zip((11, 28, 46, 65), broken, strict=True):
        rows.insert(position, row)
    return rows


def to_csv(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TEMPLATE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------- source data
def generate_source(institutions: int, students: int, seed: int) -> Path:
    out = Path(tempfile.mkdtemp(prefix="apaar-demo-"))
    print(f"Generating {institutions} institutions / {students} students into {out}")
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "generate.py",
            "--institutions",
            str(institutions),
            "--students",
            str(students),
            "--seed",
            str(seed),
            "--out",
            str(out),
        ],
        cwd=DATAGEN,
        check=True,
    )
    return out


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------- database steps
def table_counts(conn: psycopg.Connection) -> dict[str, int]:
    tables = (*RESET_TABLES, "institutions", "programmes", "seat_pools", "api_keys")
    return {
        t: conn.execute(f"select count(*) as n from public.{t}").fetchone()["n"] for t in tables
    }


def reset(conn: psycopg.Connection) -> None:
    print("Rows before reset:")
    for table, count in table_counts(conn).items():
        print(f"  {table:<24} {count}")
    for table in RESET_TABLES:
        conn.execute(f"delete from public.{table}")
    removed = conn.execute(
        "delete from public.institutions where origin = %s returning id", (ORIGIN,)
    ).fetchall()
    print(f"Deleted every row above and {len(removed)} institutions created by an earlier load")


def ensure_window(conn: psycopg.Connection, admin: User) -> dict[str, Any]:
    now = datetime.now(UTC)
    body = {
        "academic_year": YEAR,
        "opens_at": datetime(2026, 6, 1, tzinfo=UTC),
        "closes_at": max(now + timedelta(days=30), datetime(2026, 12, 31, 18, 30, tzinfo=UTC)),
    }
    window, _ = windows.upsert_window(conn, body, admin, unlock=True)
    return window


def create_institutions(
    conn: psycopg.Connection, institutions: list[dict[str, str]], intake: list[dict[str, str]]
) -> dict[str, str]:
    """Insert generated institutions, programmes and seat pools; return aicte_code -> id."""
    ids: dict[str, str] = {}
    for inst in institutions:
        row = conn.execute(
            """
            insert into public.institutions (aicte_code, name, state, parent_trust, origin)
            values (%s, %s, %s, %s, %s)
            on conflict (aicte_code) do update set name = excluded.name
            returning id
            """,
            (inst["aicte_code"], inst["name"], inst["state"], inst["parent_trust"] or None, ORIGIN),
        ).fetchone()
        ids[inst["aicte_code"]] = str(row["id"])
    programmes: dict[tuple[str, str], str] = {}
    for code, programme in sorted(
        {(r["institution_aicte_code"], r["programme_code"]) for r in intake}
    ):
        pg = programme.startswith("PG")
        row = conn.execute(
            """
            insert into public.programmes (institution_id, code, name, level, duration_years)
            values (%s, %s, %s, %s, %s)
            on conflict (institution_id, code) do update set name = excluded.name
            returning id
            """,
            (
                ids[code],
                programme,
                PROGRAMME_NAMES.get(programme, programme),
                "PG" if pg else "UG",
                2 if pg else 4,
            ),
        ).fetchone()
        programmes[(code, programme)] = str(row["id"])
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into public.seat_pools
              (programme_id, academic_year, pool, approved_seats, rule_version)
            values (%s, %s, %s, %s, %s)
            on conflict (programme_id, academic_year, pool, rule_version) do nothing
            """,
            [
                (
                    programmes[(r["institution_aicte_code"], r["programme_code"])],
                    r["academic_year"],
                    r["seat_pool"],
                    int(r["approved_seats"]),
                    r["rule_version"],
                )
                for r in intake
            ],
        )
    return ids


def operator(institution_id: str) -> User:
    return User(
        id="demo-institution_operator",
        role="institution_operator",
        institution_id=institution_id,
        display_name="Demo institution operator",
        demo=True,
    )


# Broadcasts go out on a side thread so the next batch does not wait for them.
BROADCASTS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="broadcast")


def load_batch(institution_id: str, file_name: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    """Upload and commit one file through the services, in two transactions like the API.

    Each transaction runs in psycopg pipeline mode: statements whose results are not read
    straight away (row inserts, findings, audit inserts, locks) share one round trip. Over
    the Supabase session pooler a round trip can take hundreds of milliseconds, so this is
    what keeps the default load under 5 minutes. The service logic is unchanged.
    """
    settings = get_settings()
    user = operator(institution_id)
    with transaction() as conn, conn.pipeline():
        result, _ = batch_service.upload(conn, user, file_name, to_csv(rows), settings)
    if result["missing_required"]:
        raise SystemExit(f"{file_name}: required columns not mapped {result['missing_required']}")
    with transaction() as conn, conn.pipeline():
        committed, events = batch_service.commit(conn, result["batch"]["id"], user, settings)
    BROADCASTS.submit(realtime.publish, events)
    return committed


Job = tuple[str, str, list[dict[str, str]]]  # (institution_id, file name, rows)


def chains(jobs: list[Job]) -> list[list[Job]]:
    """Group jobs whose files share any APAAR ID; keep the given order inside each group.

    DUP_CROSS_INSTITUTION depends on which of two institutions commits first, so jobs that
    share an APAAR run one after another in a fixed order. Jobs with no APAAR in common
    cannot change each other's findings and may run at the same time. The result is the
    same as loading every job sequentially in the given order.
    """
    parent = list(range(len(jobs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[str, int] = {}
    for index, (_, _, rows) in enumerate(jobs):
        for row in rows:
            apaar = row.get("apaar_id")
            if not apaar:
                continue
            if apaar in owner:
                parent[find(index)] = find(owner[apaar])
            else:
                owner[apaar] = index
    groups: dict[int, list[Job]] = defaultdict(list)
    for index, job in enumerate(jobs):
        groups[find(index)].append(job)
    # Longest chains first so the pool stays busy until the end.
    return sorted(groups.values(), key=lambda g: -sum(len(j[2]) for j in g))


def run_chains(groups: list[list[Job]], workers: int) -> dict[str, dict[str, Any]]:
    def run(group: list[Job]) -> list[tuple[str, dict[str, Any]]]:
        return [(name, load_batch(inst, name, rows)) for inst, name, rows in group if rows]

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="load") as pool:
        for done in pool.map(run, groups):
            results.update(done)
    return results


# ---------------------------------------------------------------------------- reporting
def shadow_story(conn: psycopg.Connection, batch_id: str) -> dict[str, int]:
    findings = Counter(
        {
            r["rule_code"]: r["rows"]
            for r in conn.execute(
                "select rule_code, count(distinct row_number) as rows from public.validation_issues"
                " where batch_id = %s group by 1",
                (batch_id,),
            ).fetchall()
        }
    )
    batch = conn.execute(
        "select commit_result from public.batches where id = %s", (batch_id,)
    ).fetchone()
    overrun = conn.execute(
        """
        select count(*) as n, max((evidence->>'overrun_by')::int) as overrun_by
        from public.review_cases
        where kind = 'intake_overrun' and institution_id = %s and evidence->>'programme' = 'UG-CSE'
        """,
        (SHADOW,),
    ).fetchone()
    signals = conn.execute(
        "select count(*) as n from public.review_cases where kind = 'signal'"
        " and institution_id = %s and evidence->>'batch_id' = %s",
        (SHADOW, batch_id),
    ).fetchone()["n"]
    ledger = conn.execute(
        """
        select count(*) as admitted from public.admissions a
        join public.programmes p on p.id = a.programme_id
        where a.active and p.institution_id = %s and p.code = 'UG-CSE' and a.academic_year = %s
        """,
        (SHADOW, YEAR),
    ).fetchone()
    blind_matches = conn.execute(
        """
        select count(*) as n from public.review_cases
        where kind = 'blind_match'
          and array[evidence->>'institution_a_id', evidence->>'institution_b_id']
              @> array[%s::text, %s::text]
        """,
        (SHADOW, NARMADA),
    ).fetchone()["n"]
    approved = conn.execute(
        """
        select sum(approved_seats) as seats from (
          select distinct on (sp.pool) sp.approved_seats from public.seat_pools sp
          join public.programmes p on p.id = sp.programme_id
          where p.institution_id = %s and p.code = 'UG-CSE' and sp.academic_year = %s
          order by sp.pool, sp.rule_version desc) x
        """,
        (SHADOW, YEAR),
    ).fetchone()
    return {
        "admitted": ledger["admitted"],
        "approved": int(approved["seats"] or 0),
        "overrun_cases": overrun["n"],
        "overrun_by": overrun["overrun_by"] or 0,
        "contact_cluster": findings["SHARED_CONTACT_CLUSTER"],
        "after_cutoff": findings["ADMISSION_AFTER_CUTOFF"],
        "cross_institution": findings["DUP_CROSS_INSTITUTION"],
        "signal_cases": signals,
        "opted_out": findings["APAAR_OPTED_OUT"],
        "rejected": batch["commit_result"]["rows_rejected"],
        "blind_match_with_narmada": blind_matches,
    }


def summary(conn: psycopg.Connection) -> dict[str, Any]:
    def one(sql: str) -> int:
        return conn.execute(sql).fetchone()["n"]

    cases = conn.execute(
        "select kind, count(*) as n from public.review_cases group by 1 order by 1"
    ).fetchall()
    return {
        "institutions": one("select count(*) as n from public.institutions"),
        "students": one("select count(*) as n from public.students"),
        "admissions": one("select count(*) as n from public.admissions where active"),
        "review_cases": {r["kind"]: r["n"] for r in cases},
        "audit_events": one("select count(*) as n from public.audit_events"),
        "audit_verify": audit_store.verify(conn),
    }


TYPO_DETAILS = re.compile(r"^[^;]+; '(?P<copy>.*)' vs '(?P<source>.*)' at (?P<code>\S+)$")


def planted_typo_pairs(
    generated: list[dict[str, str]], truth: list[dict[str, str]]
) -> list[tuple[dict[str, str], dict[str, str]]]:
    """(copy row, source row) for each planted typo_duplicate in ground_truth.csv.

    ground_truth names the copy row (R0000123 is data row 123); the source is the row at the
    named institution with the original name, the same date of birth and the same guardian.
    """
    pairs = []
    seen: set[str] = set()
    for entry in truth:
        if entry["anomaly_type"] != "typo_duplicate" or entry["record_id"] in seen:
            continue
        seen.add(entry["record_id"])
        details = TYPO_DETAILS.match(entry["details"])
        copy = generated[int(entry["record_id"].lstrip("R")) - 1]
        if details is None:
            continue
        source = next(
            (
                r
                for r in generated
                if r["institution_aicte_code"] == details["code"]
                and r["student_name"] == details["source"]
                and r["dob"] == copy["dob"]
                and r["guardian_name"] == copy["guardian_name"]
            ),
            None,
        )
        if source is not None:
            pairs.append((copy, source))
    return pairs


def scripted_typo_pairs(
    shadow: list[dict[str, str]], source: dict[str, str]
) -> list[tuple[dict[str, str], dict[str, str]]]:
    """(copy row, source row) for the Blind Match pair load_demo scripts itself: the Shadow row
    that typo_copy made from ``source`` (a Narmada student)."""
    name = misspell(source["student_name"])
    return [
        (row, source)
        for row in shadow
        if row["student_name"] == name and row["dob"] == source["dob"]
    ]


def match_quality(
    planted: set[str],
    scripted: set[str],
    cases: set[str],
    planted_total: int,
    scripted_total: int,
) -> dict[str, Any]:
    """Precision and recall of blind_match cases (pair keys) against the expected pairs.

    Expected pairs are the planted ground-truth pairs plus the scripted ones; ``planted`` and
    ``scripted`` hold only pairs whose two students were both loaded. Precision is true cases
    over all blind_match cases, recall is true cases over all expected pairs.
    """
    expected = planted | scripted
    hits = len(cases & expected)
    return {
        "planted": planted_total,
        "planted_loaded": len(planted),
        "planted_found": len(cases & planted),
        "scripted": scripted_total,
        "scripted_found": len(cases & scripted),
        "cases": len(cases),
        "true_positives": hits,
        "precision": hits / len(cases) if cases else None,
        "recall": hits / len(expected) if expected else None,
    }


def blind_match_quality(
    conn: psycopg.Connection,
    pairs: list[tuple[dict[str, str], dict[str, str]]],
    scripted: list[tuple[dict[str, str], dict[str, str]]],
) -> dict[str, Any]:
    """Precision and recall of blind_match cases against the planted typo duplicates and the
    scripted Shadow-Narmada pair."""
    rows = [r for pair in [*pairs, *scripted] for r in pair]
    apaars = [r["apaar_id"] for r in rows if r["apaar_id"]]
    provisionals = [r["provisional_id"] for r in rows if r["provisional_id"]]
    found = conn.execute(
        "select id, apaar_id, provisional_id from public.students"
        " where apaar_id = any(%s) or provisional_id = any(%s)",
        (apaars, provisionals),
    ).fetchall()
    ids = {f["apaar_id"] or f["provisional_id"]: str(f["id"]) for f in found}

    def student(row: dict[str, str]) -> str | None:
        return ids.get(row["apaar_id"] or row["provisional_id"])

    def keys(source: list[tuple[dict[str, str], dict[str, str]]]) -> set[str]:
        return {
            blind_match.pair_key(a, b)
            for a, b in ((student(c), student(s)) for c, s in source)
            if a and b and a != b
        }

    cases = {
        r["k"]
        for r in conn.execute(
            "select evidence->>'pair_key' as k from public.review_cases"
            " where kind = 'blind_match' and evidence ? 'pair_key'"
        ).fetchall()
    }
    return match_quality(keys(pairs), keys(scripted), cases, len(pairs), len(scripted))


def mark_demo_student(conn: psycopg.Connection) -> str | None:
    """Mark one clean Meghdoot student whose only admission is still submitted as the demo
    student (shared/credentials.md section 10), with one access-log entry for the upload."""
    row = conn.execute(
        """
        select s.id from public.students s
        join public.admissions a on a.student_id = s.id and a.active
        join public.programmes p on p.id = a.programme_id
        where p.institution_id = %s and p.code = 'UG-CSE' and a.pool = 'regular'
          and a.status = 'submitted' and s.apaar_id is not null and not s.opted_out
          and (select count(*) from public.admissions x where x.student_id = s.id) = 1
          and not exists (
            select 1 from public.review_cases rc where rc.kind = 'blind_match'
              and s.id::text in (rc.evidence->>'student_a_id', rc.evidence->>'student_b_id'))
        order by s.apaar_id limit 1
        """,
        (MEGHDOOT,),
    ).fetchone()
    conn.execute("update public.students set is_demo = false where is_demo")
    if row is None:
        return None
    conn.execute("update public.students set is_demo = true where id = %s", (row["id"],))
    conn.execute(
        """
        insert into public.access_log (student_id, accessor, accessor_role, purpose, fields)
        values (%s, 'Meghdoot Institute of Engineering', 'institution_operator',
                'Admission record upload', array['full_name', 'dob', 'apaar_id'])
        """,
        (row["id"],),
    )
    return str(row["id"])


def integrity_lowest() -> list[dict[str, Any]] | str:
    """Run app.services.integrity.compute_and_save_integrity if it exists and return the 5
    lowest-scoring institutions, or the reason it was skipped. Never raises."""
    try:
        from app.services import integrity

        compute = getattr(integrity, "compute_and_save_integrity", None)
        if compute is None:
            return "app.services.integrity has no compute_and_save_integrity"
        with transaction() as conn:
            compute(conn)
            return conn.execute(
                """
                select i.name, s.score::float as score, s.tier from (
                  select distinct on (institution_id) institution_id, score, tier
                  from public.integrity_scores where academic_year = %s
                  order by institution_id, computed_at desc) s
                join public.institutions i on i.id = s.institution_id
                order by s.score, i.name limit 5
                """,
                (YEAR,),
            ).fetchall()
    except Exception as exc:  # noqa: BLE001 - the Integrity Score must never fail the load
        return f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------- main
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="Delete demo data first")
    parser.add_argument("--yes", action="store_true", help="Confirm --reset")
    parser.add_argument("--institutions", type=int, default=25, help="Generated institutions")
    parser.add_argument("--students", type=int, default=5000, help="Generated admissions")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Institutions loaded in parallel (independent ones only); 1 loads one at a time",
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Existing datagen output folder; default runs datagen into a temp folder",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.reset and not args.yes:
        print("--reset deletes every admission, batch, case and audit event; add --yes.")
        return 2
    settings = get_settings()
    if not settings.database_url or not settings.pseudonym_secret:
        print("DATABASE_URL and PSEUDONYM_SECRET must be set in backend/.env")
        return 2
    started = time.perf_counter()
    admin = User(
        id="demo-aicte_admin", role="aicte_admin", display_name="Demo AICTE admin", demo=True
    )

    source = args.source or generate_source(args.institutions, args.students, args.seed)
    institutions = read_csv(source / "institutions.csv")
    intake = read_csv(source / "intake.csv")
    generated = read_csv(source / "admissions.csv")
    by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in generated:
        by_code[row["institution_aicte_code"]].append(row)

    with transaction() as conn:
        if args.reset:
            reset(conn)
            audit_store.append_event(conn, admin.id, "demo.reset", "dataset", None, {})
        window = ensure_window(conn, admin)
        ids = create_institutions(conn, institutions, intake)
    print(f"Window {YEAR}: {window['state']} until {window['closes_at']:%Y-%m-%d}")

    gen = Scripted(args.seed, {r["apaar_id"] for r in generated if r["apaar_id"]})
    meghdoot = gen.clean(MEGHDOOT, MEGHDOOT_PLAN, block=1)
    narmada = gen.clean(NARMADA, NARMADA_PLAN, block=2)
    twins = [r for r in narmada if r["programme_code"] == "UG-CSE" and r["seat_pool"] == "regular"]
    # twins[6] is the Narmada student deck/demo/shadow-late-batch.csv misspells.
    shadow = shadow_rows(gen, twins[3:5], twins[5])

    # Meghdoot, Narmada and the generated institutions first (independent ones in parallel,
    # see chains), then Shadow on its own, after Narmada, so its duplicates and story hold.
    first: list[Job] = [
        (MEGHDOOT, "meghdoot-admissions-2026-27.csv", meghdoot),
        (NARMADA, "narmada-admissions-2026-27.csv", narmada),
        *[(ids[code], f"admissions-{code}-2026-27.csv", by_code[code]) for code in sorted(ids)],
    ]
    last: Job = (SHADOW, "shadow-cse-admissions-2026-27.csv", shadow)
    results = run_chains(chains(first), max(1, args.workers))
    results.update(run_chains([[last]], 1))
    for _, name, _ in [*first, last]:
        if name not in results:
            continue
        result = results[name]
        print(
            f"  {name:<44} committed {result['rows_committed']:>4}"
            f"  rejected {result['rows_rejected']:>2}  cases {len(result['review_cases_created'])}"
        )

    with transaction() as conn:
        scan = blind_match.scan_all(conn)
    BROADCASTS.submit(realtime.publish, scan.pop("events", []))
    lowest = integrity_lowest()
    truth_file = source / "ground_truth.csv"
    pairs = planted_typo_pairs(generated, read_csv(truth_file)) if truth_file.exists() else []
    with transaction() as conn:
        story = shadow_story(conn, results["shadow-cse-admissions-2026-27.csv"]["batch_id"])
        quality = blind_match_quality(conn, pairs, scripted_typo_pairs(shadow, twins[5]))
        demo_student = mark_demo_student(conn)
        totals = summary(conn)
    BROADCASTS.shutdown(wait=True)
    close_pool()

    print("\nShadow Institute of Technology, UG-CSE 2026-27:")
    expected = {**SHADOW_STORY, "overrun_cases": 1, "signal_cases": 2}
    for key, value in story.items():
        mark = "ok" if expected.get(key) == value else f"EXPECTED {expected.get(key)}"
        print(f"  {key:<24} {value:>4}  {mark}")
    print("\nTotals:")
    print(f"  institutions       {totals['institutions']}")
    print(f"  students           {totals['students']}")
    print(f"  admissions         {totals['admissions']}")
    for kind, count in totals["review_cases"].items():
        print(f"  cases {kind:<12} {count}")
    print(f"  audit events       {totals['audit_events']}")
    print("\nBlind Match (cross-institution):")
    if not settings.blind_match_secret:
        print("  skipped: BLIND_MATCH_SECRET is empty")
    new_cases = len(scan["cases_created"])
    print(f"  blind_match cases  {quality['cases']}  (new in this scan {new_cases})")
    print(
        f"  planted pairs found  {quality['planted_found']}/{quality['planted']}"
        f"  (both students loaded {quality['planted_loaded']})"
    )
    print(f"  scripted pairs found {quality['scripted_found']}/{quality['scripted']}")
    for key in ("precision", "recall"):
        value = quality[key]
        print(f"  {key:<18} {'n/a' if value is None else f'{value:.2f}'}")
    print("\nIntegrity Score:")
    if isinstance(lowest, str):
        print(f"  integrity: skipped ({lowest})")
    else:
        print("  5 lowest-scoring institutions:")
        for row in lowest:
            print(f"  {row['score']:>6.1f}  {row['tier']:<10} {row['name']}")
    print(f"  demo student       {demo_student or 'NOT MARKED'}")
    print(f"  /audit/verify      {totals['audit_verify']}")
    print(f"  run time           {time.perf_counter() - started:.1f} s")
    story_ok = all(expected.get(k) == v for k, v in story.items())
    return 0 if story_ok and totals["audit_verify"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
