# Owner: Dev A
"""Service orchestrating student identity encoding, linkage, and duplicate detection."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from engine.blind_match.encoder import (
    DEFAULT_FIELD_WEIGHTS,
    encode_identity,
    extract_birth_year,
    hash_birth_year,
)
from engine.blind_match.linkage import find_linkage_matches
from engine.blind_match.models import (
    InMemoryReviewCaseRepository,
    ReviewCaseRepository,
    StudentRecord,
)
from engine.config import MATCH_THRESHOLD
from engine.types import EncodedRecord, MatchCase

__all__ = [
    "BlindMatchService",
    "find_exact_apaar_duplicates",
]


def find_exact_apaar_duplicates(records: list[Any]) -> list[MatchCase]:
    """Identify students with identical non-empty APAAR IDs across different institutions."""
    by_apaar: dict[str, list[Any]] = {}

    for r in records:
        apaar = getattr(r, "apaar_id", None)
        if apaar is None and isinstance(r, dict):
            apaar = r.get("apaar_id")
        if not apaar:
            continue
        clean_apaar = str(apaar).strip()
        if clean_apaar:
            by_apaar.setdefault(clean_apaar, []).append(r)

    matches: list[MatchCase] = []
    for _apaar, group in by_apaar.items():
        if len(group) < 2:
            continue
        n = len(group)
        for i in range(n):
            for j in range(i + 1, n):
                r1 = group[i]
                r2 = group[j]

                inst_1 = getattr(r1, "institution_id", None) or (
                    r1.get("institution_id") if isinstance(r1, dict) else ""
                )
                inst_2 = getattr(r2, "institution_id", None) or (
                    r2.get("institution_id") if isinstance(r2, dict) else ""
                )

                if inst_1 and inst_2 and inst_1 != inst_2:
                    s1 = (
                        getattr(r1, "student_id", None)
                        or getattr(r1, "record_id", None)
                        or (
                            r1.get("student_id") or r1.get("record_id")
                            if isinstance(r1, dict)
                            else ""
                        )
                    )
                    s2 = (
                        getattr(r2, "student_id", None)
                        or getattr(r2, "record_id", None)
                        or (
                            r2.get("student_id") or r2.get("record_id")
                            if isinstance(r2, dict)
                            else ""
                        )
                    )

                    matches.append(
                        MatchCase(
                            case_id=str(uuid4()),
                            institution_a=str(inst_1),
                            institution_b=str(inst_2),
                            student_a_id=str(s1),
                            student_b_id=str(s2),
                            similarity_score=1.0,
                            confidence=1.0,
                            matched_fields=["apaar_id"],
                            status="open",
                            created_at=datetime.now(UTC),
                        )
                    )
    return matches


class BlindMatchService:
    """Core Blind Match engine for privacy-preserving duplicate record linkage."""

    def __init__(
        self,
        secret: bytes | str | None = None,
        threshold: float | None = None,
        review_repo: ReviewCaseRepository | None = None,
        field_weights: dict[str, float] | None = None,
    ) -> None:
        raw_secret = secret or os.getenv("BLIND_MATCH_SECRET")
        if not raw_secret:
            raise ValueError(
                "BlindMatchService requires a secret key. Pass `secret` or set BLIND_MATCH_SECRET."
            )
        if isinstance(raw_secret, str):
            self.secret = raw_secret.encode("utf-8")
        else:
            self.secret = bytes(raw_secret)

        self.threshold = threshold if threshold is not None else MATCH_THRESHOLD
        self.review_repo = review_repo or InMemoryReviewCaseRepository()
        self.field_weights = field_weights or DEFAULT_FIELD_WEIGHTS

    def encode_student(self, student: StudentRecord | dict[str, Any]) -> EncodedRecord:
        """Convert a student into a Bloom-filter EncodedRecord without raw identity fields."""
        if isinstance(student, StudentRecord):
            rec_id = student.student_id
            inst_id = student.institution_id
            fields = student.to_identity_fields()
            salt = student.birth_year
            apaar = student.apaar_id
        else:
            rec_id = str(student.get("student_id") or student.get("record_id") or uuid4())
            inst_id = str(student.get("institution_id", ""))
            fields = {
                "student_name": student.get("student_name") or student.get("full_name") or "",
                "dob": student.get("dob") or student.get("date_of_birth") or "",
                "father_name": student.get("father_name") or student.get("guardian_name") or "",
                "mother_name": student.get("mother_name") or "",
            }
            salt = extract_birth_year(fields.get("dob"))
            apaar = student.get("apaar_id")

        bloom_bytes = encode_identity(
            fields=fields,
            secret=self.secret,
            bits=1024,
            k=20,
            field_weights=self.field_weights,
            salt=salt,
        )
        b_year_hash = hash_birth_year(salt, self.secret)

        return EncodedRecord(
            record_id=rec_id,
            institution_id=inst_id,
            bloom=bloom_bytes,
            birth_year_hash=b_year_hash,
            apaar_id=apaar,
        )

    def encode_students(
        self, students: list[StudentRecord | dict[str, Any]]
    ) -> list[EncodedRecord]:
        """Batch encode a list of student records."""
        return [self.encode_student(s) for s in students]

    def find_fuzzy_matches(
        self,
        records: list[EncodedRecord],
        threshold: float | None = None,
    ) -> list[MatchCase]:
        """Find candidate duplicate pairs across different institutions via Dice similarity."""
        t = threshold if threshold is not None else self.threshold
        linkage_matches = find_linkage_matches(records, threshold=t)
        # Filter for cross-institution potential duplicates
        cross_inst_matches = [m for m in linkage_matches if not m.same_institution]
        return [m.to_match_case() for m in cross_inst_matches]

    def run_blind_match(
        self,
        records: list[StudentRecord | dict[str, Any]],
        threshold: float | None = None,
    ) -> list[MatchCase]:
        """Execute full Blind Match pipeline: exact APAAR and privacy-preserving fuzzy linkage."""

        t = threshold if threshold is not None else self.threshold

        # 1. Exact APAAR matches across institutions
        exact_matches = find_exact_apaar_duplicates(records)

        # 2. Encode records into privacy-preserving Bloom filters
        encoded = self.encode_students(records)

        # 3. Fuzzy linkage matches
        fuzzy_matches = self.find_fuzzy_matches(encoded, threshold=t)

        # 4. Deduplicate (if pair already flagged by exact APAAR, keep exact match)
        seen_pairs: set[tuple[str, str]] = set()
        for m in exact_matches:
            pair = tuple(sorted([m.student_a_id, m.student_b_id]))
            seen_pairs.add(pair)

        all_matches: list[MatchCase] = list(exact_matches)
        for m in fuzzy_matches:
            pair = tuple(sorted([m.student_a_id, m.student_b_id]))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                all_matches.append(m)

        # 5. Persist to review repository interface if configured
        if self.review_repo:
            for match in all_matches:
                self.review_repo.create_case(match)

        return all_matches

    def create_review_case(self, case: MatchCase) -> str:
        """Persist a review case through the repository abstraction."""
        return self.review_repo.create_case(case)
