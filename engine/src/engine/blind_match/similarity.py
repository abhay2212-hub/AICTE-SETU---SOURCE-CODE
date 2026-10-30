# Owner: Dev A
"""Dice similarity coefficient for Bloom-filter bit arrays."""

from __future__ import annotations

from typing import Any


def dice(a: bytes | Any, b: bytes | Any) -> float:
    """Dice coefficient of two equal-length bit arrays: 2 * |A and B| / (|A| + |B|).

    Returns 1.0 when neither array has any bit set.
    Accepts bytes or objects with a `data` attribute returning bytes.
    """
    raw_a = a.data if hasattr(a, "data") else a
    raw_b = b.data if hasattr(b, "data") else b

    if not isinstance(raw_a, (bytes, bytearray)) or not isinstance(raw_b, (bytes, bytearray)):
        raise TypeError("Inputs must be bytes, bytearray, or possess a .data bytes attribute")

    if len(raw_a) != len(raw_b):
        raise ValueError("Bloom filters must have the same length")

    int_a = int.from_bytes(raw_a, "big")
    int_b = int.from_bytes(raw_b, "big")

    total = int_a.bit_count() + int_b.bit_count()
    if total == 0:
        return 1.0

    return 2.0 * (int_a & int_b).bit_count() / total


def jaccard(a: bytes | Any, b: bytes | Any) -> float:
    """Jaccard similarity coefficient: |A and B| / |A or B|."""
    raw_a = a.data if hasattr(a, "data") else a
    raw_b = b.data if hasattr(b, "data") else b

    if len(raw_a) != len(raw_b):
        raise ValueError("Bloom filters must have the same length")

    int_a = int.from_bytes(raw_a, "big")
    int_b = int.from_bytes(raw_b, "big")

    union = (int_a | int_b).bit_count()
    if union == 0:
        return 1.0

    return (int_a & int_b).bit_count() / union
