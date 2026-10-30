# Owner: Dev B
"""Fake engine functions that follow shared/engine-hooks.md, for unit tests while engine/ on
main is still stubs."""

from __future__ import annotations

import hashlib
import hmac
import re
from functools import lru_cache

from engine.types import Signal


@lru_cache(maxsize=65536)
def _gram_bits(secret: bytes, gram: str, bits: int, k: int) -> int:
    digest = hmac.new(secret, gram.encode(), hashlib.sha256).digest()
    h1, h2 = int.from_bytes(digest[:8], "big"), int.from_bytes(digest[8:16], "big") | 1
    mask = 0
    for i in range(k):
        mask |= 1 << ((h1 + i * h2) % bits)
    return mask


def encode_identity(fields: dict[str, str], secret: bytes, bits: int = 1024, k: int = 20) -> bytes:
    """Bigram Bloom filter keyed with ``secret``, as the encoder docstring describes."""
    assert secret, "the hook must pass BLIND_MATCH_SECRET explicitly"
    assert all(isinstance(v, str) for v in fields.values()), "fields must be strings"
    bloom = 0
    for name, value in fields.items():
        text = " " + " ".join(re.sub(r"[^a-z0-9 ]", "", value.lower()).split()) + " "
        for i in range(len(text) - 1):
            bloom |= _gram_bits(secret, f"{name}:{text[i : i + 2]}", bits, k)
    return bloom.to_bytes(bits // 8, "big")


def eligibility(rows: list[dict]) -> list[Signal]:
    """QUALIFYING_BELOW_NORM for every row under 45 percent."""
    low = [
        r["row_number"]
        for r in rows
        if r["qualifying_exam_pct"] is not None and r["qualifying_exam_pct"] < 45
    ]
    if not low:
        return []
    evidence = {"row_numbers": low, "reason": "Qualifying percentage below the AICTE minimum."}
    return [Signal("QUALIFYING_BELOW_NORM", "batch", "warning", evidence)]


def backdating(rows: list[dict]) -> list[Signal]:
    """BACKDATED_ENTRY for rows admitted more than 300 days before upload_date."""
    from datetime import date

    old = [
        r["row_number"]
        for r in rows
        if r["admission_date"] is not None
        and (date.fromisoformat(r["upload_date"]) - date.fromisoformat(r["admission_date"])).days
        > 300
    ]
    if not old:
        return []
    evidence = {"row_numbers": old, "reason": "Entered long after the admission date."}
    return [Signal("BACKDATED_ENTRY", "batch", "review", evidence)]
