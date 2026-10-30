# Owner: Dev C
"""Synthetic admissions data with planted anomalies for the APAAR Integrity Platform.

All output is synthetic. APAAR IDs start with 9999; phone numbers and emails are fake.

    uv run python generate.py --small
    uv run python generate.py --institutions 200 --students 50000 --seed 42 --out out/
"""

from __future__ import annotations

import argparse
import csv
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from faker import Faker

ACADEMIC_YEAR = "2026-27"
RULE_VERSION = "APH-2026-27-v1"
WINDOW_START, WINDOW_END = date(2026, 7, 15), date(2026, 9, 15)
BACKDATE_START, BACKDATE_END = date(2026, 3, 1), date(2026, 5, 31)
SHARED = Path(__file__).resolve().parent.parent / "shared" / "csv"
ADMISSION_COLUMNS = (
    (SHARED / "admissions-template.csv").read_text(encoding="utf-8").strip().split(",")
)
INTAKE_COLUMNS = (SHARED / "intake-template.csv").read_text(encoding="utf-8").strip().split(",")

STATES = [
    "Andhra Pradesh",
    "Assam",
    "Bihar",
    "Chhattisgarh",
    "Delhi",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Madhya Pradesh",
    "Maharashtra",
    "Odisha",
    "Punjab",
    "Rajasthan",
    "Tamil Nadu",
    "Telangana",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]
PROGRAMMES = {
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
UG_EXAMS = ["JEE Main", "MHT CET", "KCET", "TNEA", "WBJEE", "AP EAPCET"]
PG_EXAMS = {"PG-MBA": ["CAT", "MAT", "CMAT"], "PG-MCA": ["NIMCET", "MAH MCA CET"]}
FOREIGN = ["US", "GB", "AE", "NP", "CA", "AU", "SG"]
POOLS = ("regular", "tfw", "fn_oci_pio", "nri")


@dataclass
class Pool:
    institution: dict
    programme: str
    pool: str
    approved: int
    rows: list[dict] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.institution['aicte_code']}|{self.programme}|{ACADEMIC_YEAR}|{self.pool}"


class Generator:
    def __init__(self, n_institutions: int, n_students: int, seed: int) -> None:
        self.n_institutions = n_institutions
        self.n_students = n_students
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.fake = Faker("en_IN")
        self.fake.seed_instance(seed)
        self.apaar_pool = iter(self.np_rng.permutation(10**8))
        self.provisional_seq = Counter()
        self.ground_truth: list[tuple[object, str, str]] = []
        self.dup_sources: set[int] = (
            set()
        )  # rows whose APAAR is duplicated; never opt them out  # (row or pool key, type, details)

    # ------------------------------------------------------------------ helpers
    def new_apaar(self) -> str:
        return f"9999{next(self.apaar_pool):08d}"

    def new_provisional(self, institution: dict) -> str:
        code = institution["aicte_code"]
        self.provisional_seq[code] += 1
        return f"PROV-{code}-{self.provisional_seq[code]:04d}"

    def rand_date(self, start: date, end: date) -> date:
        return start + timedelta(days=self.rng.randint(0, (end - start).days))

    def mark(self, target: object, anomaly: str, details: str) -> None:
        self.ground_truth.append((target, anomaly, details))

    # ------------------------------------------------------------------ institutions
    def institutions(self) -> list[dict]:
        trusts = [f"{self.fake.last_name()} Education Trust" for _ in range(3)]
        result = []
        for i in range(1, self.n_institutions + 1):
            city = self.fake.city()
            kind = self.rng.choice(
                [
                    "Institute of Technology",
                    "College of Engineering",
                    "Institute of Engineering and Management",
                ]
            )
            shared_trust = self.rng.random() < 0.12
            result.append(
                {
                    "aicte_code": f"1-99{i:05d}",
                    "name": f"{city} {kind}",
                    "state": self.rng.choice(STATES),
                    "parent_trust": self.rng.choice(trusts)
                    if shared_trust
                    else f"{city} {self.fake.last_name()} Shiksha Samiti",
                }
            )
        return result

    def pools(self, institutions: list[dict]) -> list[Pool]:
        raw = []
        for inst in institutions:
            codes = self.rng.sample(sorted(PROGRAMMES), self.rng.randint(2, 5))
            for code in codes:
                raw.append((inst, code, self.rng.choice([60, 120, 180])))
        # Scale intake so the requested number of students fills roughly 90% of seats.
        scale = self.n_students / (0.9 * sum(total for _, _, total in raw))
        pools = []
        for inst, code, total in raw:
            total = max(20, int(round(total * scale / 10)) * 10)
            side = max(1, total // 20)  # 5% each for tfw, fn_oci_pio, nri
            split = {"regular": total - 3 * side, "tfw": side, "fn_oci_pio": side, "nri": side}
            pools += [Pool(inst, code, p, split[p]) for p in POOLS]
        return pools

    # ------------------------------------------------------------------ students
    def student(self, pool: Pool) -> dict:
        gender = self.rng.choices(["male", "female", "transgender"], [0.6, 0.395, 0.005])[0]
        first = self.fake.first_name_female() if gender == "female" else self.fake.first_name_male()
        last = self.fake.last_name()
        pg = pool.programme.startswith("PG")
        dob = (
            self.rand_date(date(2001, 1, 1), date(2004, 6, 30))
            if pg
            else self.rand_date(date(2007, 6, 1), date(2009, 5, 31))
        )
        fn = pool.pool == "fn_oci_pio"
        oci = fn and self.rng.random() < 0.5
        mode = (
            "management"
            if pool.pool == "nri"
            else self.rng.choices(
                ["cap", "management", "spot", "lateral"], [0.75, 0.15, 0.07, 0.03]
            )[0]
        )
        exam = self.rng.choice(PG_EXAMS[pool.programme]) if pg else self.rng.choice(UG_EXAMS)
        return {
            "institution_aicte_code": pool.institution["aicte_code"],
            "programme_code": pool.programme,
            "academic_year": ACADEMIC_YEAR,
            "student_name": f"{first} {last}",
            "dob": dob.isoformat(),
            "gender": gender,
            "category": self.rng.choices(
                ["general", "ews", "obc", "sc", "st"], [0.4, 0.08, 0.3, 0.15, 0.07]
            )[0],
            "pwd": str(self.rng.random() < 0.03).lower(),
            "apaar_id": self.new_apaar(),
            "apaar_opt_out": "false",
            "provisional_id": "",
            "nationality": self.rng.choice(FOREIGN) if fn else "IN",
            "oci_status": str(oci).lower(),
            "fn_status": str(fn and not oci).lower(),
            "nri_category": str(pool.pool == "nri").lower(),
            "seat_pool": pool.pool,
            "admission_mode": mode,
            "admission_date": self.rand_date(WINDOW_START, WINDOW_END).isoformat(),
            "qualifying_exam": exam,
            "qualifying_exam_pct": f"{self.rng.uniform(45, 99):.2f}",
            "domicile_state": pool.institution["state"]
            if self.rng.random() < 0.7
            else self.rng.choice(STATES),
            "contact_phone": f"+9198{self.rng.randrange(10**8):08d}",
            "contact_email": f"{first}.{last}{self.rng.randrange(10**4)}@example.com".lower(),
            "guardian_name": f"{self.fake.first_name_male()} {last}",
        }

    def fill(self, pools: list[Pool]) -> None:
        capacity = sum(p.approved for p in pools)
        rate = min(1.0, self.n_students / capacity)
        targets = [
            min(p.approved, int(p.approved * rate * self.rng.uniform(0.92, 1.0))) for p in pools
        ]
        shortfall = self.n_students - sum(targets)
        open_pools = [i for i, p in enumerate(pools) if targets[i] < p.approved]
        while shortfall > 0 and open_pools:
            i = self.rng.choice(open_pools)
            targets[i] += 1
            shortfall -= 1
            if targets[i] >= pools[i].approved:
                open_pools.remove(i)
        for pool, target in zip(pools, targets, strict=True):
            pool.rows = [self.student(pool) for _ in range(target)]

    # ------------------------------------------------------------------ anomalies
    def plant(self, pools: list[Pool]) -> None:
        n = self.n_students
        regular = [p for p in pools if p.pool == "regular"]
        everyone = [(p, r) for p in pools for r in p.rows]

        # Intake overruns: fill a regular pool past its approved seats.
        for pool in self.rng.sample(regular, max(1, len(regular) // 30)):
            while len(pool.rows) < pool.approved:
                pool.rows.append(self.student(pool))
            extra = max(2, int(pool.approved * self.rng.uniform(0.1, 0.25)))
            pool.rows += [self.student(pool) for _ in range(extra)]
            self.mark(
                pool.key, "intake_overrun", f"approved={pool.approved} admitted={len(pool.rows)}"
            )

        # Exact cross-institution APAAR duplicates: same person admitted at two institutions.
        for _ in range(max(2, n // 500)):
            src_pool, src = self.rng.choice(everyone)
            dst = self.room_elsewhere(regular, src_pool)
            if dst is None:
                continue
            copy = self.student(dst)
            for key in (
                "student_name",
                "dob",
                "gender",
                "category",
                "apaar_id",
                "guardian_name",
                "domicile_state",
                "contact_phone",
                "contact_email",
            ):
                copy[key] = src[key]
            dst.rows.append(copy)
            self.dup_sources.add(id(src))
            self.mark(
                copy,
                "dup_cross_institution",
                f"apaar {src['apaar_id']} also at {src['institution_aicte_code']}",
            )

        # Typo duplicates: same person, misspelled name, different or missing APAAR.
        for _ in range(max(2, n // 400)):
            src_pool, src = self.rng.choice(everyone)
            dst = self.room_elsewhere(regular, src_pool)
            if dst is None:
                continue
            copy = self.student(dst)
            for key in ("dob", "gender", "category", "guardian_name", "domicile_state"):
                copy[key] = src[key]
            copy["student_name"] = self.misspell(src["student_name"])
            if self.rng.random() < 0.5:
                how = "different apaar"
            else:
                copy.update(
                    apaar_id="",
                    apaar_opt_out="true",
                    provisional_id=self.new_provisional(dst.institution),
                )
                how = "missing apaar"
            dst.rows.append(copy)
            self.dup_sources.add(id(src))
            self.mark(
                copy,
                "typo_duplicate",
                f"{how}; '{copy['student_name']}' vs '{src['student_name']}' "
                f"at {src['institution_aicte_code']}",
            )

        # Shared-contact clusters: many students at one institution share a phone and email.
        candidates = [p for p in regular if len(p.rows) >= 12]
        for _ in range(max(1, n // 2000) if candidates else 0):
            pool = self.rng.choice(candidates)
            members = self.rng.sample(pool.rows, self.rng.randint(6, min(12, len(pool.rows))))
            phone = f"+9197{self.rng.randrange(10**8):08d}"
            email = f"admissions.desk{self.rng.randrange(10**4)}@example.com"
            for row in members:
                row["contact_phone"], row["contact_email"] = phone, email
                self.mark(row, "shared_contact_cluster", f"cluster of {len(members)} on {phone}")

        # Backdated entries: admission dates months before the admission window.
        for _pool, row in self.rng.sample(everyone, max(3, n // 300)):
            row["admission_date"] = self.rand_date(BACKDATE_START, BACKDATE_END).isoformat()
            row["admission_mode"] = "management"
            self.mark(row, "backdated_entry", f"admission_date {row['admission_date']}")

        # Opted-out students: no APAAR, provisional ID instead. Must never be an error.
        for pool, row in self.rng.sample(everyone, max(3, n // 70)):
            if row["apaar_opt_out"] == "true" or id(row) in self.dup_sources:
                continue
            row.update(
                apaar_id="",
                apaar_opt_out="true",
                provisional_id=self.new_provisional(pool.institution),
            )
            self.mark(row, "opted_out", f"provisional_id {row['provisional_id']}")

    def room_elsewhere(self, pools: list[Pool], src: Pool) -> Pool | None:
        """A pool at another institution with a free seat, so duplicates cause no overrun."""
        options = [
            p for p in pools if p.institution is not src.institution and len(p.rows) < p.approved
        ]
        return self.rng.choice(options) if options else None

    def misspell(self, name: str) -> str:
        chars = list(name)
        positions = [i for i, c in enumerate(chars) if c.isalpha() and i > 0]
        i = self.rng.choice(positions)
        op = self.rng.choice(["drop", "swap", "double"])
        if op == "drop":
            del chars[i]
        elif op == "swap" and i + 1 < len(chars) and chars[i + 1].isalpha():
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        else:
            chars.insert(i, chars[i])
        return "".join(chars)

    # ------------------------------------------------------------------ output
    def write(self, out: Path) -> Counter:
        institutions = self.institutions()
        pools = self.pools(institutions)
        self.fill(pools)
        self.plant(pools)
        out.mkdir(parents=True, exist_ok=True)

        rows = sorted(
            (r for p in pools for r in p.rows),
            key=lambda r: (r["institution_aicte_code"], r["programme_code"]),
        )
        record_ids = {id(r): f"R{i:07d}" for i, r in enumerate(rows, start=1)}

        write_csv(
            out / "institutions.csv", ["aicte_code", "name", "state", "parent_trust"], institutions
        )
        write_csv(
            out / "intake.csv",
            INTAKE_COLUMNS,
            [
                {
                    "institution_aicte_code": p.institution["aicte_code"],
                    "programme_code": p.programme,
                    "academic_year": ACADEMIC_YEAR,
                    "seat_pool": p.pool,
                    "approved_seats": p.approved,
                    "rule_version": RULE_VERSION,
                }
                for p in pools
            ],
        )
        write_csv(out / "admissions.csv", ADMISSION_COLUMNS, rows)
        truth = [
            {
                "record_id": t if isinstance(t, str) else record_ids[id(t)],
                "anomaly_type": a,
                "details": d,
            }
            for t, a, d in self.ground_truth
        ]
        write_csv(out / "ground_truth.csv", ["record_id", "anomaly_type", "details"], truth)

        print(
            f"Wrote {len(institutions)} institutions, {len(pools)} seat pools, "
            f"{len(rows)} admissions to {out}"
        )
        return Counter(t["anomaly_type"] for t in truth)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--institutions", type=int, default=200)
    parser.add_argument("--students", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--small", action="store_true", help="5 institutions, 300 students")
    args = parser.parse_args()
    if args.small:
        args.institutions, args.students = 5, 300
    counts = Generator(args.institutions, args.students, args.seed).write(args.out)
    print("Planted anomalies:")
    for anomaly, count in sorted(counts.items()):
        print(f"  {anomaly:<24} {count}")


if __name__ == "__main__":
    main()
