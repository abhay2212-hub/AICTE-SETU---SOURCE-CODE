# Owner: Dev A
"""Privacy-preserving Blind Match engine for cross-institution duplicate detection."""

from __future__ import annotations

from engine.blind_match.encoder import (
    DEFAULT_FIELD_WEIGHTS,
    derive_bit_positions,
    encode_identity,
    encode_student,
    extract_birth_year,
    generate_bigrams,
    hash_birth_year,
    normalize_text,
)
from engine.blind_match.linkage import (
    BirthYearBlocking,
    block_records,
    calculate_confidence,
    find_candidates,
    find_linkage_matches,
)
from engine.blind_match.models import (
    BlockingStrategy,
    BloomFilter,
    InMemoryReviewCaseRepository,
    LinkageMatch,
    ReviewCaseRepository,
    StudentRecord,
)
from engine.blind_match.service import BlindMatchService, find_exact_apaar_duplicates
from engine.blind_match.similarity import dice, jaccard

__all__ = [
    "DEFAULT_FIELD_WEIGHTS",
    "BirthYearBlocking",
    "BlindMatchService",
    "BlockingStrategy",
    "BloomFilter",
    "InMemoryReviewCaseRepository",
    "LinkageMatch",
    "ReviewCaseRepository",
    "StudentRecord",
    "block_records",
    "calculate_confidence",
    "derive_bit_positions",
    "dice",
    "encode_identity",
    "encode_student",
    "extract_birth_year",
    "find_candidates",
    "find_exact_apaar_duplicates",
    "find_linkage_matches",
    "generate_bigrams",
    "hash_birth_year",
    "jaccard",
    "normalize_text",
]
