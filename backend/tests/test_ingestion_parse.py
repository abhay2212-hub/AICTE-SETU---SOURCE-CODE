# Owner: Dev B
import io
from datetime import date

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services.ingestion import (
    HASH_PREFIX,
    REQUIRED_COLUMNS,
    TEMPLATE_COLUMNS,
    check_mapping,
    hash_contact,
    normalize_row,
    parse_upload,
    sanitize_raw,
    suggest_mapping,
)

SECRET = "test-pseudonym-secret"
LIMITS = {"max_mb": 5, "max_rows": 100}


def csv_bytes(text: str, bom: bool = False) -> bytes:
    data = text.encode("utf-8")
    return b"\xef\xbb\xbf" + data if bom else data


# ---------------------------------------------------------------- parse
def test_csv_reads_everything_as_strings():
    parsed = parse_upload("a.csv", csv_bytes("apaar_id,pct\n009912340001,07.50\n"), **LIMITS)
    assert parsed.headers == ["apaar_id", "pct"]
    assert parsed.rows == [{"apaar_id": "009912340001", "pct": "07.50"}]
    assert len(parsed.file_hash) == 64


def test_csv_with_bom():
    parsed = parse_upload(
        "a.csv", csv_bytes("student_name,dob\nA,2008-01-01\n", bom=True), **LIMITS
    )
    assert parsed.headers == ["student_name", "dob"]


def test_xlsx_first_sheet():
    wb = Workbook()
    ws = wb.active
    ws.append(["Student Name", "APAAR No", "DOB"])
    ws.append(["Priya Kumari", "999912340004", date(2008, 1, 30)])
    wb.create_sheet("ignored").append(["x"])
    buffer = io.BytesIO()
    wb.save(buffer)
    parsed = parse_upload("a.xlsx", buffer.getvalue(), **LIMITS)
    assert parsed.headers == ["Student Name", "APAAR No", "DOB"]
    assert parsed.rows[0]["APAAR No"] == "999912340004"
    assert parsed.rows[0]["DOB"].startswith("2008-01-30")


def test_other_types_rejected_with_415():
    with pytest.raises(HTTPException) as err:
        parse_upload("a.pdf", b"%PDF", **LIMITS)
    assert err.value.status_code == 415


def test_size_limit_413():
    with pytest.raises(HTTPException) as err:
        parse_upload("a.csv", b"x" * (1024 * 1024 + 1), max_mb=1, max_rows=10)
    assert err.value.status_code == 413


def test_row_limit_422():
    body = "a\n" + "1\n" * 11
    with pytest.raises(HTTPException) as err:
        parse_upload("a.csv", body.encode(), max_mb=1, max_rows=10)
    assert err.value.status_code == 422


def test_unreadable_file_422():
    with pytest.raises(HTTPException) as err:
        parse_upload("a.xlsx", b"not a workbook", **LIMITS)
    assert err.value.status_code == 422


# ---------------------------------------------------------------- mapping
@pytest.mark.parametrize(
    ("header", "target"),
    [
        ("APAAR", "apaar_id"),
        ("apaar_no", "apaar_id"),
        ("ABC ID", "apaar_id"),
        ("Date of Birth", "dob"),
        ("DOB", "dob"),
        ("Name", "student_name"),
        ("Student", "student_name"),
        ("Mobile", "contact_phone"),
        ("Phone", "contact_phone"),
        ("E-mail", "contact_email"),
        ("Seat-Pool", "seat_pool"),
        ("  admission_date ", "admission_date"),
    ],
)
def test_header_synonyms(header, target):
    assert suggest_mapping([header]).mapping == {header: target}


def test_unmapped_and_missing_required():
    suggestion = suggest_mapping(["Name", "Favourite Colour"])
    assert suggestion.unmapped == ["Favourite Colour"]
    assert "student_name" not in suggestion.missing_required
    assert "dob" in suggestion.missing_required


def test_full_template_maps_completely():
    suggestion = suggest_mapping(TEMPLATE_COLUMNS)
    assert suggestion.missing_required == []
    assert set(suggestion.mapping.values()) == set(TEMPLATE_COLUMNS)


def test_same_target_not_mapped_twice():
    suggestion = suggest_mapping(["Phone", "Mobile"])
    assert suggestion.mapping == {"Phone": "contact_phone"}
    assert suggestion.unmapped == ["Mobile"]


def test_check_mapping_rejects_bad_input():
    with pytest.raises(HTTPException):
        check_mapping({"Nope": "dob"}, ["Name"])
    with pytest.raises(HTTPException):
        check_mapping({"Name": "not_a_column"}, ["Name"])
    with pytest.raises(HTTPException):
        check_mapping({"A": "dob", "B": "dob"}, ["A", "B"])
    check_mapping({"Name": "student_name"}, ["Name"])


def test_required_columns_exclude_conditional_and_optional():
    for column in ("apaar_id", "provisional_id", "contact_phone", "contact_email"):
        assert column not in REQUIRED_COLUMNS


# ---------------------------------------------------------------- normalise and hash
def test_normalisation():
    raw = {
        "Name": "  priya   KUMARI ",
        "DOB": "30/01/2008",
        "Pool": " Regular ",
        "Programme": "ug-cse",
        "PwD": "No",
        "Opt Out": "1",
        "Pct": "46.234",
    }
    mapping = {
        "Name": "student_name",
        "DOB": "dob",
        "Pool": "seat_pool",
        "Programme": "programme_code",
        "PwD": "pwd",
        "Opt Out": "apaar_opt_out",
        "Pct": "qualifying_exam_pct",
    }
    v = normalize_row(raw, mapping, 1, SECRET).values
    assert v["student_name"] == "Priya Kumari"
    assert v["dob"] == date(2008, 1, 30)
    assert v["seat_pool"] == "regular"
    assert v["programme_code"] == "UG-CSE"
    assert v["pwd"] is False
    assert v["apaar_opt_out"] is True
    assert v["qualifying_exam_pct"] == 46.23
    assert v["apaar_id"] is None


def test_invalid_values_are_recorded():
    row = normalize_row({"d": "31-31-2008", "b": "maybe"}, {"d": "dob", "b": "pwd"}, 4, SECRET)
    assert row.invalid == {"dob": "31-31-2008", "pwd": "maybe"}
    assert row.row_number == 4


def test_contact_hashing_never_keeps_raw_values():
    raw = {"Mobile": "+91 98000-00001", "Email": "Aarav@Example.com"}
    row = normalize_row(raw, {"Mobile": "contact_phone", "Email": "contact_email"}, 1, SECRET)
    text = repr(row.to_json())
    assert "98000" not in text and "9800000001" not in text
    assert "example.com" not in text.lower()
    assert row.values["contact_phone"].startswith(HASH_PREFIX)
    assert row.values["contact_phone"] == hash_contact("9800000001", SECRET, "phone")
    assert row.values["contact_email"] == hash_contact("aarav@example.com", SECRET, "email")


def test_hash_is_keyed_and_prefixed():
    assert hash_contact("9800000001", "a", "phone") != hash_contact("9800000001", "b", "phone")
    already = hash_contact("9800000001", "a", "phone")
    assert hash_contact(already, "a", "phone") == already
    assert hash_contact("", "a", "phone") is None


def test_sanitize_raw_hashes_mapped_and_contact_like_columns():
    rows = [{"Mob": "9800000001", "Alt Contact": "9811111111", "Note": "a@b.co", "Name": "A"}]
    clean = sanitize_raw(rows, {"Mob": "contact_phone"}, SECRET)[0]
    assert clean["Name"] == "A"
    for header in ("Mob", "Alt Contact", "Note"):
        assert clean[header].startswith(HASH_PREFIX)
    assert "9800000001" not in repr(clean) and "a@b.co" not in repr(clean)
