# Owner: Dev A
"""Bloom-filter encoding of identity fields for privacy-preserving duplicate detection."""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from typing import Any

from engine.blind_match.models import BloomFilter, StudentRecord
from engine.blind_match.similarity import dice

__all__ = [
    "DEFAULT_FIELD_WEIGHTS",
    "derive_bit_positions",
    "dice",
    "encode_identity",
    "encode_student",
    "extract_birth_year",
    "generate_bigrams",
    "hash_birth_year",
    "normalize_text",
]

DEFAULT_FIELD_WEIGHTS: dict[str, float] = {
    "student_name": 1.0,
    "dob": 2.0,
    "father_name": 1.0,
    "mother_name": 1.0,
}

FIELD_ALIASES: dict[str, str] = {
    "student_name": "student_name",
    "name": "student_name",
    "full_name": "student_name",
    "dob": "dob",
    "date_of_birth": "dob",
    "birth_date": "dob",
    "father_name": "father_name",
    "fathers_name": "father_name",
    "father": "father_name",
    "guardian_name": "father_name",
    "mother_name": "mother_name",
    "mothers_name": "mother_name",
    "mother": "mother_name",
}


def normalize_text(text: str | None) -> str:
    """Normalize text: NFKD unicode normalization, lowercase, strip punctuation and whitespace."""
    if not text:
        return ""
    # Unicode NFKD normalization to decompose accents / ligatures
    nfkd = unicodedata.normalize("NFKD", str(text))
    # Keep alphanumeric characters and whitespace
    ascii_clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    lowered = ascii_clean.lower()
    # Remove punctuation
    no_punct = re.sub(r"[^\w\s]", "", lowered)
    # Collapse multiple whitespaces into a single space
    return re.sub(r"\s+", " ", no_punct).strip()


def generate_bigrams(text: str, padded: bool = False) -> list[str]:
    """Generate character bigrams for a normalized string.

    Example: "RAHUL" -> ["ra", "ah", "hu", "ul"]
    """
    if not text:
        return []
    s = f" {text} " if padded else text
    if len(s) < 2:
        return [s]
    return [s[i : i + 2] for i in range(len(s) - 1)]


def extract_birth_year(dob_str: str | None) -> str:
    """Extract a 4-digit birth year from dob string, defaulting to '0000'."""
    if not dob_str:
        return "0000"
    match = re.search(r"\b(19\d\d|20\d\d)\b", str(dob_str))
    if match:
        return match.group(1)
    return "0000"


def hash_birth_year(birth_year: str, secret: bytes) -> str:
    """Compute a deterministic 16-hex-character block key for the birth year."""
    return hmac.new(secret, birth_year.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def derive_bit_positions(
    token: str,
    secret: bytes,
    bits: int = 1024,
    k: int = 8,
) -> list[int]:
    """Derive `k` unique bit positions in [0, bits) using HMAC-SHA256 double hashing.

    Double hashing: position_i = (h1 + i * h2) mod bits.
    """
    if not secret:
        raise ValueError("A non-empty secret key must be provided for bit position derivation.")
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    digest = hmac.new(secret, token.encode("utf-8"), hashlib.sha256).digest()
    h1 = int.from_bytes(digest[:16], "big")
    # Ensure h2 is odd so gcd(h2, bits)=1 for power-of-two bit lengths
    h2 = int.from_bytes(digest[16:], "big") | 1

    positions: list[int] = []
    seen: set[int] = set()
    i = 0
    while len(positions) < k:
        pos = (h1 + i * h2) % bits
        if pos not in seen:
            seen.add(pos)
            positions.append(pos)
        i += 1
    return positions


def encode_identity(
    fields: dict[str, str],
    secret: bytes,
    bits: int = 1024,
    k: int = 8,
    field_weights: dict[str, float] | None = None,
    salt: str | None = None,
) -> bytes:
    """Encode identity fields into a Bloom filter of ``bits`` bits.

    Algorithm:
    1. Normalise each field value (lowercase, strip accents and punctuation, collapse spaces).
    2. Salt each field using the student's birth year.
    3. Split each value into character bigrams (excluding the birth year from DOB bigrams).
    4. For each bigram, derive ``k`` bit positions with HMAC-SHA256 keyed by ``secret``
       using double hashing: position_i = (h1 + i * h2) mod bits.
    5. Set those bits and return the filter as ``bits // 8`` bytes.
    """
    if not secret:
        raise ValueError("A non-empty secret key must be provided for Blind Match encoding.")
    if isinstance(secret, str):
        secret = secret.encode("utf-8")

    weights = field_weights or DEFAULT_FIELD_WEIGHTS

    # Determine birth year salt
    birth_year = salt
    if not birth_year:
        dob_raw = fields.get("dob") or fields.get("date_of_birth") or fields.get("birth_date")
        birth_year = extract_birth_year(dob_raw)

    bitmask = 0

    for raw_field_name, raw_val in fields.items():
        if not raw_val:
            continue
        field_key = raw_field_name.strip().lower()
        canonical_name = FIELD_ALIASES.get(field_key, field_key)
        if canonical_name == "dob":
            # Exclude birth year from DOB bigrams; birth year is already in the salt prefix
            val_to_bigram = re.sub(r"\b(19\d\d|20\d\d)\b", "", str(raw_val)).strip("-/ ")
        else:
            val_to_bigram = raw_val
        norm_val = normalize_text(val_to_bigram)
        if not norm_val:
            continue

        weight = weights.get(canonical_name, 1.0)
        k_field = max(1, int(round(k * weight)))
        bigrams = generate_bigrams(norm_val)

        for bigram in bigrams:
            # Salt with birth year and scope with canonical field name
            token = f"{birth_year}:{canonical_name}:{bigram}"
            positions = derive_bit_positions(token, secret, bits=bits, k=k_field)
            for pos in positions:
                bitmask |= 1 << pos

    byte_length = (bits + 7) // 8
    return bitmask.to_bytes(byte_length, "big")


def encode_student(
    student: StudentRecord | dict[str, Any],
    secret: bytes,
    bits: int = 1024,
    k: int = 8,
    field_weights: dict[str, float] | None = None,
) -> BloomFilter:
    """Encode a student record into a typed BloomFilter object."""
    if not secret:
        raise ValueError("A non-empty secret key must be provided for student encoding.")

    if isinstance(student, StudentRecord):
        fields = student.to_identity_fields()
        salt = student.birth_year
    else:
        fields = {
            "student_name": student.get("student_name") or student.get("full_name") or "",
            "dob": student.get("dob") or student.get("date_of_birth") or "",
            "father_name": student.get("father_name") or student.get("guardian_name") or "",
            "mother_name": student.get("mother_name") or "",
        }
        salt = extract_birth_year(fields.get("dob"))

    raw_bytes = encode_identity(
        fields=fields,
        secret=secret,
        bits=bits,
        k=k,
        field_weights=field_weights,
        salt=salt,
    )
    return BloomFilter.from_bytes(raw_bytes, bits=bits)
