# Owner: Dev A
"""Domain models and interfaces for the Blind Match engine."""

from __future__ import annotations

import base64
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from engine.blind_match.similarity import dice
from engine.types import MatchCase


@dataclass(frozen=True)
class BloomFilter:
    """Immutable representation of a Bloom filter bit array."""

    data: bytes
    bits: int = 1024

    def __post_init__(self) -> None:
        expected_bytes = (self.bits + 7) // 8
        if len(self.data) != expected_bytes:
            raise ValueError(
                f"Data length {len(self.data)} bytes != expected {expected_bytes} bytes "
                f"for {self.bits} bits"
            )

    @property
    def bit_count(self) -> int:
        """Return the number of set bits (popcount)."""
        return int.from_bytes(self.data, "big").bit_count()

    def to_bytes(self) -> bytes:
        return self.data

    def to_b64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @classmethod
    def from_bytes(cls, data: bytes, bits: int = 1024) -> BloomFilter:
        return cls(data=bytes(data), bits=bits)

    @classmethod
    def from_b64(cls, b64_str: str, bits: int = 1024) -> BloomFilter:
        return cls(data=base64.b64decode(b64_str), bits=bits)

    def intersection(self, other: BloomFilter) -> BloomFilter:
        if self.bits != other.bits:
            raise ValueError("Bloom filters must have identical bit lengths")
        int_a = int.from_bytes(self.data, "big")
        int_b = int.from_bytes(other.data, "big")
        intersect_int = int_a & int_b
        return BloomFilter(
            data=intersect_int.to_bytes((self.bits + 7) // 8, "big"),
            bits=self.bits,
        )

    def union(self, other: BloomFilter) -> BloomFilter:
        if self.bits != other.bits:
            raise ValueError("Bloom filters must have identical bit lengths")
        int_a = int.from_bytes(self.data, "big")
        int_b = int.from_bytes(other.data, "big")
        union_int = int_a | int_b
        return BloomFilter(
            data=union_int.to_bytes((self.bits + 7) // 8, "big"),
            bits=self.bits,
        )

    def dice(self, other: BloomFilter) -> float:
        return dice(self, other)

    def __len__(self) -> int:
        return self.bits

    def __repr__(self) -> str:
        return f"BloomFilter(bits={self.bits}, set_bits={self.bit_count})"


@dataclass(frozen=True)
class StudentRecord:
    """Canonical student identity record to be encoded and matched."""

    student_id: str
    institution_id: str
    student_name: str
    dob: str
    father_name: str = ""
    mother_name: str = ""
    apaar_id: str | None = None

    @property
    def birth_year(self) -> str:
        """Extract 4-digit birth year from dob string."""
        match = re.search(r"\b(19\d\d|20\d\d)\b", self.dob)
        if match:
            return match.group(1)
        return "0000"

    def to_identity_fields(self) -> dict[str, str]:
        """Convert into a field dictionary suitable for the Bloom filter encoder."""
        return {
            "student_name": self.student_name,
            "dob": self.dob,
            "father_name": self.father_name,
            "mother_name": self.mother_name,
        }


@dataclass
class LinkageMatch:
    """Candidate duplicate match detected by the linkage engine."""

    record_a: str
    record_b: str
    institution_a: str
    institution_b: str
    similarity_score: float
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    matched_fields: list[str] = field(
        default_factory=lambda: ["student_name", "dob", "father_name", "mother_name"]
    )
    same_institution: bool = False
    case_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_match_case(self) -> MatchCase:
        return MatchCase(
            case_id=self.case_id,
            institution_a=self.institution_a,
            institution_b=self.institution_b,
            student_a_id=self.record_a,
            student_b_id=self.record_b,
            similarity_score=round(self.similarity_score, 4),
            confidence=round(self.confidence, 4),
            matched_fields=self.matched_fields,
            status="open",
            created_at=self.created_at,
        )


class BlockingStrategy(ABC):
    """Abstract strategy for partitioning records into blocks before pairwise comparison."""

    @abstractmethod
    def get_block_key(self, record: Any) -> str:
        """Return block key string for the given record."""
        ...


class ReviewCaseRepository(ABC):
    """Interface abstraction for creating and retrieving duplicate review cases."""

    @abstractmethod
    def create_case(self, case: MatchCase) -> str:
        """Persist a review case and return its ID."""
        ...

    @abstractmethod
    def get_case(self, case_id: str) -> MatchCase | None:
        """Retrieve a review case by ID."""
        ...

    @abstractmethod
    def list_cases(self, status: str | None = None) -> list[MatchCase]:
        """List cases optionally filtered by status."""
        ...


class InMemoryReviewCaseRepository(ReviewCaseRepository):
    """In-memory implementation of ReviewCaseRepository for tests and local development."""

    def __init__(self) -> None:
        self._cases: dict[str, MatchCase] = {}

    def create_case(self, case: MatchCase) -> str:
        self._cases[case.case_id] = case
        return case.case_id

    def get_case(self, case_id: str) -> MatchCase | None:
        return self._cases.get(case_id)

    def list_cases(self, status: str | None = None) -> list[MatchCase]:
        if status is None:
            return list(self._cases.values())
        return [c for c in self._cases.values() if c.status == status]
