# Owner: Dev A
import pytest

from engine.blind_match.encoder import (
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
    BloomFilter,
    InMemoryReviewCaseRepository,
    StudentRecord,
)
from engine.blind_match.service import BlindMatchService, find_exact_apaar_duplicates
from engine.blind_match.similarity import dice, jaccard
from engine.types import EncodedRecord, MatchCase

SECRET = b"test-secret-key-for-blind-match-32b"


# --- 1. Text Normalization ---


def test_normalize_text_unicode_accents() -> None:
    assert normalize_text("Renée") == "renee"
    assert normalize_text("Zoë") == "zoe"
    assert normalize_text("München") == "munchen"


def test_normalize_text_punctuation_and_whitespace() -> None:
    assert normalize_text("Dr. B.R. Ambedkar") == "dr br ambedkar"
    assert normalize_text("O'Connor-Smith") == "oconnorsmith"
    assert normalize_text("   Rahul    Kumar   ") == "rahul kumar"


def test_normalize_text_empty_and_none() -> None:
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


# --- 2. Bigram Generation ---


def test_generate_bigrams_standard() -> None:
    # Matches the exact specification example: "RAHUL" -> RA, AH, HU, UL
    assert generate_bigrams("rahul") == ["ra", "ah", "hu", "ul"]


def test_generate_bigrams_padded() -> None:
    assert generate_bigrams("rahul", padded=True) == [" r", "ra", "ah", "hu", "ul", "l "]


def test_generate_bigrams_short_and_empty() -> None:
    assert generate_bigrams("a") == ["a"]
    assert generate_bigrams("") == []


# --- 3. Birth Year Extraction and Hashing ---


def test_extract_birth_year() -> None:
    assert extract_birth_year("2004-05-15") == "2004"
    assert extract_birth_year("15/08/1999") == "1999"
    assert extract_birth_year("InvalidDate") == "0000"
    assert extract_birth_year(None) == "0000"


def test_hash_birth_year_deterministic() -> None:
    h1 = hash_birth_year("2004", SECRET)
    h2 = hash_birth_year("2004", SECRET)
    h3 = hash_birth_year("2005", SECRET)
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16


# --- 4. HMAC Double Hashing and Bit Positions ---


def test_derive_bit_positions_properties() -> None:
    positions = derive_bit_positions("2004:student_name:ra", SECRET, bits=1024, k=20)
    assert len(positions) == 20
    assert len(set(positions)) == 20  # All 20 positions are unique
    assert all(0 <= p < 1024 for p in positions)


def test_derive_bit_positions_determinism() -> None:
    p1 = derive_bit_positions("2004:student_name:ra", SECRET, bits=1024, k=20)
    p2 = derive_bit_positions("2004:student_name:ra", SECRET, bits=1024, k=20)
    p3 = derive_bit_positions("2004:student_name:ah", SECRET, bits=1024, k=20)
    assert p1 == p2
    assert p1 != p3


# --- 5. Bloom Filter Encoding & Determinism ---


def test_bloom_filter_determinism() -> None:
    fields = {
        "student_name": "Rahul Sharma",
        "dob": "2004-05-15",
        "father_name": "Vijay Sharma",
        "mother_name": "Sunita Sharma",
    }
    raw1 = encode_identity(fields, SECRET, bits=1024, k=20)
    raw2 = encode_identity(fields, SECRET, bits=1024, k=20)
    assert raw1 == raw2
    assert len(raw1) == 128  # 1024 bits // 8


def test_bloom_filter_different_students_differ() -> None:
    s1 = {
        "student_name": "Rahul Sharma",
        "dob": "2004-05-15",
        "father_name": "Vijay Sharma",
        "mother_name": "Sunita Sharma",
    }
    s2 = {
        "student_name": "Ananya Verma",
        "dob": "2004-08-20",
        "father_name": "Rajesh Verma",
        "mother_name": "Pooja Verma",
    }
    bf1 = encode_identity(s1, SECRET)
    bf2 = encode_identity(s2, SECRET)
    assert bf1 != bf2
    sim = dice(bf1, bf2)
    from engine.config import MATCH_THRESHOLD

    assert sim < MATCH_THRESHOLD  # Different identities fall well below the match threshold (0.85)
    assert sim < 0.75


def test_bloom_filter_object_methods() -> None:
    student = StudentRecord(
        student_id="s1",
        institution_id="inst-1",
        student_name="Rahul Sharma",
        dob="2004-05-15",
        father_name="Vijay Sharma",
        mother_name="Sunita Sharma",
    )
    bf = encode_student(student, SECRET)
    assert isinstance(bf, BloomFilter)
    assert len(bf) == 1024
    assert bf.bit_count > 0

    # Serialization roundtrip
    b64 = bf.to_b64()
    bf_from_b64 = BloomFilter.from_b64(b64, bits=1024)
    assert bf == bf_from_b64

    # Intersection and Union
    inter = bf.intersection(bf)
    assert inter.bit_count == bf.bit_count
    union = bf.union(bf)
    assert union.bit_count == bf.bit_count


# --- 6. Dice and Jaccard Similarity ---


def test_dice_similarity_known_values() -> None:
    a = bytes([0b11110000, 0b00001111])
    b = bytes([0b11110000, 0b00001111])
    assert dice(a, b) == 1.0

    c = bytes([0b00001111, 0b11110000])
    assert dice(a, c) == 0.0

    # Partial overlap: a has 8 bits, d has 8 bits, 4 bits in common
    d = bytes([0b11000000, 0b00000011, 0b11110000, 0b00000000])
    e = bytes([0b11110000, 0b00001111, 0b00000000, 0b00000000])
    assert dice(d, e) == pytest.approx(2 * 4 / (8 + 8))

    # BloomFilter object input
    bf_a = BloomFilter.from_bytes(a, bits=16)
    bf_b = BloomFilter.from_bytes(b, bits=16)
    assert bf_a.dice(bf_b) == 1.0


def test_jaccard_similarity() -> None:
    a = bytes([0b11000000])  # 2 bits
    b = bytes([0b10100000])  # 2 bits, 1 shared
    assert jaccard(a, b) == pytest.approx(1 / 3)


# --- 7. Blocking & Linkage Engine ---


def test_birth_year_blocking() -> None:
    r1 = EncodedRecord("1", "inst-1", bytes(128), "hash_2004")
    r2 = EncodedRecord("2", "inst-2", bytes(128), "hash_2004")
    r3 = EncodedRecord("3", "inst-3", bytes(128), "hash_2005")

    blocks = block_records([r1, r2, r3], BirthYearBlocking())
    assert len(blocks) == 2
    assert len(blocks["hash_2004"]) == 2
    assert len(blocks["hash_2005"]) == 1


def test_linkage_matches_and_threshold_filtering() -> None:
    service = BlindMatchService(secret=SECRET, threshold=0.80)

    s1 = StudentRecord(
        "s1", "inst-a", "Rahul Sharma", "2004-05-15", "Vijay Sharma", "Sunita Sharma"
    )
    # Same student with minor typo in mother name
    s2 = StudentRecord("s2", "inst-b", "Rahul Sharma", "2004-05-15", "Vijay Sharma", "Sunit Sharma")
    # Different student in same birth year
    s3 = StudentRecord("s3", "inst-c", "Pooja Verma", "2004-11-20", "Anil Verma", "Kavita Verma")

    rec1 = service.encode_student(s1)
    rec2 = service.encode_student(s2)
    rec3 = service.encode_student(s3)

    candidates = find_candidates([rec1, rec2, rec3], threshold=0.80)
    assert len(candidates) == 1
    assert candidates[0].record_a == "s1"
    assert candidates[0].record_b == "s2"
    assert candidates[0].dice >= 0.85

    linkage_matches = find_linkage_matches([rec1, rec2, rec3], threshold=0.80)
    assert len(linkage_matches) == 1
    match = linkage_matches[0]
    assert match.record_a == "s1"
    assert match.record_b == "s2"
    assert match.institution_a == "inst-a"
    assert match.institution_b == "inst-b"
    assert match.confidence > 0.5


def test_linkage_skips_same_apaar_id() -> None:
    # Pairs with same non-empty APAAR ID are skipped from fuzzy candidates (rule 3)
    service = BlindMatchService(secret=SECRET, threshold=0.70)
    s1 = StudentRecord(
        "s1",
        "inst-a",
        "Rahul Sharma",
        "2004-05-15",
        "Vijay Sharma",
        "Sunita Sharma",
        apaar_id="999900000001",
    )
    s2 = StudentRecord(
        "s2",
        "inst-b",
        "Rahul Sharma",
        "2004-05-15",
        "Vijay Sharma",
        "Sunita Sharma",
        apaar_id="999900000001",
    )
    rec1 = service.encode_student(s1)
    rec2 = service.encode_student(s2)

    candidates = find_candidates([rec1, rec2], threshold=0.70)
    assert len(candidates) == 0  # Skipped because APAAR IDs are identical


# --- 8. Exact APAAR Duplicate Detection ---


def test_exact_apaar_duplicate_detection() -> None:
    s1 = StudentRecord("s1", "inst-a", "Rahul Sharma", "2004-05-15", apaar_id="999911112222")
    s2 = StudentRecord("s2", "inst-b", "Rahul Sharma", "2004-05-15", apaar_id="999911112222")
    # Same institution
    s3 = StudentRecord("s3", "inst-a", "Other Student", "2004-05-15", apaar_id="999911112222")
    s4 = StudentRecord("s4", "inst-c", "No Apaar Student", "2004-05-15", apaar_id=None)

    cases = find_exact_apaar_duplicates([s1, s2, s3, s4])
    # Expect s1 (inst-a) and s2 (inst-b) to match across institutions
    # Also s2 (inst-b) and s3 (inst-a)
    assert len(cases) == 2
    for case in cases:
        assert isinstance(case, MatchCase)
        assert case.similarity_score == 1.0
        assert case.confidence == 1.0
        assert case.matched_fields == ["apaar_id"]
        assert case.institution_a != case.institution_b


# --- 9. Review Case Repository Interface ---


def test_review_case_repository_interface() -> None:
    repo = InMemoryReviewCaseRepository()
    case = MatchCase(
        institution_a="inst-1",
        institution_b="inst-2",
        student_a_id="stud-1",
        student_b_id="stud-2",
        similarity_score=0.92,
        confidence=0.85,
        matched_fields=["name", "dob"],
        status="open",
    )
    case_id = repo.create_case(case)
    assert case_id == case.case_id

    retrieved = repo.get_case(case_id)
    assert retrieved is not None
    assert retrieved.similarity_score == 0.92

    cases = repo.list_cases(status="open")
    assert len(cases) == 1
    assert repo.list_cases(status="dismissed") == []


# --- 10. End-to-End Service Run ---


def test_service_run_blind_match_pipeline() -> None:
    repo = InMemoryReviewCaseRepository()
    service = BlindMatchService(secret=SECRET, threshold=0.85, review_repo=repo)

    # Pair 1: Exact APAAR duplicate across institutions
    s1 = StudentRecord(
        "s1",
        "inst-1",
        "Aarav Patel",
        "2004-01-10",
        "Suresh Patel",
        apaar_id="999988887777",
    )
    s2 = StudentRecord(
        "s2",
        "inst-2",
        "Aarav Patel",
        "2004-01-10",
        "Suresh Patel",
        apaar_id="999988887777",
    )

    # Pair 2: Privacy-preserving fuzzy duplicate across institutions (different APAAR or opt-out)
    s3 = StudentRecord("s3", "inst-1", "Sneha Iyer", "2004-06-25", "Venkatesh Iyer", "Lakshmi Iyer")
    s4 = StudentRecord("s4", "inst-2", "Sneha Iyer", "2004-06-25", "Venkatesh Iyer", "Laxmi Iyer")

    # Pair 3: Non-matching student
    s5 = StudentRecord("s5", "inst-3", "Rohan Gupta", "2004-09-30", "Manoj Gupta", "Anita Gupta")

    all_matches = service.run_blind_match([s1, s2, s3, s4, s5])
    assert len(all_matches) == 2

    # Verify both cases were created in review repository
    assert len(repo.list_cases()) == 2

    # Check that confidence calculation works
    assert calculate_confidence(0.95, 0.85) > 0.80
    assert calculate_confidence(0.80, 0.85) == 0.0


def test_blind_match_service_requires_secret(monkeypatch) -> None:
    monkeypatch.delenv("BLIND_MATCH_SECRET", raising=False)
    with pytest.raises(ValueError, match="BLIND_MATCH_SECRET"):
        BlindMatchService(secret=None)


def test_blind_match_dob_year_exclusion_false_positive_rejection() -> None:
    """Verify that different DOBs for same name fall below 0.85 threshold."""
    # Ishita Chaudhary with different DOBs: previously scored 0.872 (false positive at 0.85)
    f1 = {"student_name": "Ishita Chaudhary", "dob": "2008-09-11"}
    f2 = {"student_name": "Ishita Chaudhary", "dob": "2008-03-09"}

    # Name typo with same DOB: should match above 0.85
    f3 = {"student_name": "Ishita Chadhary", "dob": "2008-09-11"}

    b1 = encode_identity(f1, SECRET)
    b2 = encode_identity(f2, SECRET)
    b3 = encode_identity(f3, SECRET)

    diff_dob_score = dice(b1, b2)
    typo_score = dice(b1, b3)

    assert diff_dob_score < 0.85  # No longer false positive!
    assert typo_score >= 0.85  # True match still detected
