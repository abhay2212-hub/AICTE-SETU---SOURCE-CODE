# Owner: Dev A
"""Candidate generation and linkage engine over encoded records."""

from __future__ import annotations

from typing import Any

from engine.blind_match.encoder import extract_birth_year
from engine.blind_match.models import BlockingStrategy, LinkageMatch
from engine.blind_match.similarity import dice
from engine.types import EncodedRecord, MatchCandidate

__all__ = [
    "BirthYearBlocking",
    "block_records",
    "calculate_confidence",
    "find_candidates",
    "find_linkage_matches",
]


class BirthYearBlocking(BlockingStrategy):
    """Block records by their hashed birth year."""

    def get_block_key(self, record: Any) -> str:
        if hasattr(record, "birth_year_hash") and record.birth_year_hash:
            return str(record.birth_year_hash)
        if hasattr(record, "birth_year") and record.birth_year:
            return str(record.birth_year)
        if hasattr(record, "dob") and record.dob:
            return extract_birth_year(str(record.dob))
        return "default"


def block_records(
    records: list[Any],
    strategy: BlockingStrategy | None = None,
) -> dict[str, list[Any]]:
    """Group records into blocks based on the given blocking strategy."""
    strat = strategy or BirthYearBlocking()
    blocks: dict[str, list[Any]] = {}
    for rec in records:
        key = strat.get_block_key(rec)
        blocks.setdefault(key, []).append(rec)
    return blocks


def calculate_confidence(similarity_score: float, threshold: float) -> float:
    """Calculate confidence in [0.0, 1.0] as a function of score margin over threshold."""
    if similarity_score < threshold:
        return 0.0
    margin = similarity_score - threshold
    available = 1.0 - threshold
    if available <= 0:
        return 1.0
    # Scaled confidence from 0.50 (at threshold) to 1.00 (at exact 1.0 similarity)
    conf = 0.50 + 0.50 * (margin / available)
    return min(1.0, max(0.0, conf))


def find_candidates(records: list[EncodedRecord], threshold: float) -> list[MatchCandidate]:
    """Return pairs of records whose Dice similarity is at least ``threshold``.

    Algorithm:
    1. Block records by ``birth_year_hash`` so only records with the same hashed
       birth year are compared.
    2. Within each block, compare every pair with ``encoder.dice``.
    3. Skip pairs sharing the same non-empty APAAR ID (exact duplicates are covered
       by DUP_CROSS_INSTITUTION).
    4. Emit a MatchCandidate per pair at or above ``threshold``, sorted by Dice descending.
    """
    blocks = block_records(records, BirthYearBlocking())
    candidates: list[MatchCandidate] = []

    for _block_key, block in blocks.items():
        n = len(block)
        for i in range(n):
            for j in range(i + 1, n):
                rec_a = block[i]
                rec_b = block[j]

                # Skip exact APAAR duplicates (handled separately)
                if rec_a.apaar_id and rec_b.apaar_id and rec_a.apaar_id == rec_b.apaar_id:
                    continue

                d = dice(rec_a.bloom, rec_b.bloom)
                if d >= threshold:
                    candidates.append(
                        MatchCandidate(
                            record_a=rec_a.record_id,
                            record_b=rec_b.record_id,
                            dice=round(d, 4),
                            same_institution=(rec_a.institution_id == rec_b.institution_id),
                        )
                    )

    candidates.sort(key=lambda c: c.dice, reverse=True)
    return candidates


def find_linkage_matches(
    records: list[EncodedRecord],
    threshold: float,
    strategy: BlockingStrategy | None = None,
) -> list[LinkageMatch]:
    """Return rich linkage matches with confidence, institution IDs, and evidence."""
    blocks = block_records(records, strategy or BirthYearBlocking())
    matches: list[LinkageMatch] = []

    for block_key, block in blocks.items():
        n = len(block)
        for i in range(n):
            for j in range(i + 1, n):
                rec_a = block[i]
                rec_b = block[j]

                # Skip exact APAAR duplicates (handled by exact detector)
                if rec_a.apaar_id and rec_b.apaar_id and rec_a.apaar_id == rec_b.apaar_id:
                    continue

                d = dice(rec_a.bloom, rec_b.bloom)
                if d >= threshold:
                    conf = calculate_confidence(d, threshold)
                    matches.append(
                        LinkageMatch(
                            record_a=rec_a.record_id,
                            record_b=rec_b.record_id,
                            institution_a=rec_a.institution_id,
                            institution_b=rec_b.institution_id,
                            similarity_score=round(d, 4),
                            confidence=round(conf, 4),
                            evidence={
                                "dice_score": round(d, 4),
                                "threshold": threshold,
                                "block_key": block_key,
                                "method": "bloom_filter_dice",
                            },
                            same_institution=(rec_a.institution_id == rec_b.institution_id),
                        )
                    )

    matches.sort(key=lambda m: m.similarity_score, reverse=True)
    return matches
