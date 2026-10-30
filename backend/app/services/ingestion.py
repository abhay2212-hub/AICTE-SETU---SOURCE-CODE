# Owner: Dev B
"""Upload parsing, header mapping and row normalisation. Pure functions, no database.

Raw phone numbers and emails never leave this module: contact-like cells are replaced by
HMAC-SHA256 hashes before anything is stored or returned.
"""

from __future__ import annotations

import difflib
import hashlib
import hmac
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, status

# ---------------------------------------------------------------------------- template
TEMPLATE_PATH = Path(__file__).resolve().parents[3] / "shared" / "csv" / "admissions-template.csv"
# Fallback copy for deployments that ship backend/ without shared/. Keep in sync.
_FALLBACK_COLUMNS = (
    "institution_aicte_code,programme_code,academic_year,student_name,dob,gender,category,pwd,"
    "apaar_id,apaar_opt_out,provisional_id,nationality,oci_status,fn_status,nri_category,"
    "seat_pool,admission_mode,admission_date,qualifying_exam,qualifying_exam_pct,"
    "domicile_state,contact_phone,contact_email,guardian_name"
)
TEMPLATE_COLUMNS: list[str] = (
    (TEMPLATE_PATH.read_text(encoding="utf-8") if TEMPLATE_PATH.exists() else _FALLBACK_COLUMNS)
    .strip()
    .split(",")
)

# Required per shared/csv/README.md. apaar_id and provisional_id are conditional.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "institution_aicte_code", "programme_code", "academic_year", "student_name", "dob",
    "gender", "category", "pwd", "apaar_opt_out", "nationality", "oci_status", "fn_status",
    "nri_category", "seat_pool", "admission_mode", "admission_date", "qualifying_exam",
    "qualifying_exam_pct", "domicile_state",
)  # fmt: skip

SYNONYMS: dict[str, str] = {
    "aicte_code": "institution_aicte_code",
    "institute_code": "institution_aicte_code",
    "institution_code": "institution_aicte_code",
    "programme": "programme_code",
    "program": "programme_code",
    "program_code": "programme_code",
    "course": "programme_code",
    "course_code": "programme_code",
    "year": "academic_year",
    "session": "academic_year",
    "name": "student_name",
    "student": "student_name",
    "full_name": "student_name",
    "candidate_name": "student_name",
    "date_of_birth": "dob",
    "birth_date": "dob",
    "sex": "gender",
    "caste_category": "category",
    "social_category": "category",
    "divyang": "pwd",
    "pwd_status": "pwd",
    "apaar": "apaar_id",
    "apaar_no": "apaar_id",
    "apaar_number": "apaar_id",
    "apaar_id_no": "apaar_id",
    "abc_id": "apaar_id",
    "opt_out": "apaar_opt_out",
    "apaar_optout": "apaar_opt_out",
    "provisional": "provisional_id",
    "provisional_no": "provisional_id",
    "country": "nationality",
    "oci": "oci_status",
    "foreign_national": "fn_status",
    "fn": "fn_status",
    "nri": "nri_category",
    "pool": "seat_pool",
    "quota": "seat_pool",
    "mode": "admission_mode",
    "admission_type": "admission_mode",
    "date_of_admission": "admission_date",
    "admitted_on": "admission_date",
    "exam": "qualifying_exam",
    "entrance_exam": "qualifying_exam",
    "percentage": "qualifying_exam_pct",
    "qualifying_percentage": "qualifying_exam_pct",
    "marks_pct": "qualifying_exam_pct",
    "domicile": "domicile_state",
    "state": "domicile_state",
    "mobile": "contact_phone",
    "mobile_no": "contact_phone",
    "phone": "contact_phone",
    "phone_no": "contact_phone",
    "contact_no": "contact_phone",
    "email": "contact_email",
    "email_id": "contact_email",
    "e_mail": "contact_email",
    "mail": "contact_email",
    "guardian": "guardian_name",
    "father_name": "guardian_name",
    "parent_name": "guardian_name",
}

CONTACT_FIELDS = ("contact_phone", "contact_email")
_CONTACT_HEADER_RE = re.compile(r"phone|mobile|email|e_mail|mail|contact")
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
HASH_PREFIX = "hmac:"

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------- parse
@dataclass
class ParsedUpload:
    headers: list[str]
    rows: list[dict[str, str]]
    file_hash: str


def file_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def parse_upload(file_name: str, content: bytes, *, max_mb: int, max_rows: int) -> ParsedUpload:
    """Read a CSV (UTF-8, BOM optional) or the first XLSX sheet, every cell as a string."""
    if len(content) > max_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"File is larger than {max_mb} MB")
    name = file_name.lower()
    try:
        if name.endswith(".csv"):
            frame = pd.read_csv(
                io.BytesIO(content), dtype=str, keep_default_na=False, encoding="utf-8-sig"
            )
        elif name.endswith(".xlsx"):
            frame = pd.read_excel(
                io.BytesIO(content), sheet_name=0, dtype=str, keep_default_na=False
            )
        else:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .csv or .xlsx file"
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Could not read the file"
        ) from exc
    if len(frame) > max_rows:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"File has {len(frame)} rows; the limit is {max_rows}",
        )
    headers = [str(h).strip() for h in frame.columns]
    frame.columns = headers
    rows = [
        {h: ("" if v is None else str(v)) for h, v in record.items()}
        for record in frame.to_dict(orient="records")
    ]
    return ParsedUpload(headers=headers, rows=rows, file_hash=file_sha256(content))


# ---------------------------------------------------------------------------- mapping
def normalise_header(header: str) -> str:
    text = re.sub(r"[\s\-]+", "_", header.strip().lower())
    return re.sub(r"[^a-z0-9_]", "", text).strip("_")


@dataclass
class MappingSuggestion:
    mapping: dict[str, str]
    unmapped: list[str]
    missing_required: list[str]


def suggest_mapping(headers: list[str]) -> MappingSuggestion:
    """Map uploaded headers to template columns: exact, then synonym, then close spelling."""
    mapping: dict[str, str] = {}
    unmapped: list[str] = []
    for header in headers:
        norm = normalise_header(header)
        target = norm if norm in TEMPLATE_COLUMNS else SYNONYMS.get(norm)
        if target is None:
            close = difflib.get_close_matches(norm, TEMPLATE_COLUMNS, n=1, cutoff=0.75)
            target = close[0] if close else None
        if target and target not in mapping.values():
            mapping[header] = target
        else:
            unmapped.append(header)
    return MappingSuggestion(mapping, unmapped, missing_required(mapping))


def missing_required(mapping: dict[str, str]) -> list[str]:
    mapped = set(mapping.values())
    return [c for c in REQUIRED_COLUMNS if c not in mapped]


def check_mapping(mapping: dict[str, str], headers: list[str]) -> None:
    """Reject a mapping that names unknown headers or targets, or maps a target twice."""
    unknown_headers = sorted(set(mapping) - set(headers))
    unknown_targets = sorted(set(mapping.values()) - set(TEMPLATE_COLUMNS))
    targets = list(mapping.values())
    repeated = sorted({t for t in targets if targets.count(t) > 1})
    problems = []
    if unknown_headers:
        problems.append(f"unknown headers {unknown_headers}")
    if unknown_targets:
        problems.append(f"unknown template columns {unknown_targets}")
    if repeated:
        problems.append(f"columns mapped more than once {repeated}")
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))


# ---------------------------------------------------------------------------- hashing
def hash_contact(value: str, secret: str, kind: str) -> str | None:
    """HMAC-SHA256 of a phone (digits only, last 10 for +91) or email (lowercased)."""
    if not value or not value.strip():
        return None
    if value.startswith(HASH_PREFIX):
        return value
    if kind == "phone":
        digits = re.sub(r"\D", "", value)
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        canonical = digits
    else:
        canonical = value.strip().lower()
    if not canonical:
        return None
    mac = hmac.new(secret.encode(), f"contact:{canonical}".encode(), hashlib.sha256)
    return HASH_PREFIX + mac.hexdigest()


def _contact_kind(target: str | None, header: str, value: str) -> str | None:
    if target == "contact_phone":
        return "phone"
    if target == "contact_email" or _EMAIL_RE.fullmatch(value.strip()):
        return "email"
    if _CONTACT_HEADER_RE.search(normalise_header(header)):
        return "email" if "@" in value else "phone"
    return None


def sanitize_raw(
    rows: list[dict[str, str]], mapping: dict[str, str], secret: str
) -> list[dict[str, str]]:
    """Replace every contact-like cell with its hash so raw rows are safe to store."""
    clean = []
    for row in rows:
        out = {}
        for header, value in row.items():
            kind = _contact_kind(mapping.get(header), header, value) if value else None
            out[header] = (hash_contact(value, secret, kind) or "") if kind else value
        clean.append(out)
    return clean


# ---------------------------------------------------------------------------- normalise
_TRUE = {"true", "yes", "y", "1", "t"}
_FALSE = {"false", "no", "n", "0", "f"}
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y")
BOOL_FIELDS = ("pwd", "apaar_opt_out", "oci_status", "fn_status", "nri_category")
DATE_FIELDS = ("dob", "admission_date")
UPPER_FIELDS = ("institution_aicte_code", "programme_code", "nationality", "provisional_id")
LOWER_FIELDS = ("gender", "category", "seat_pool", "admission_mode")
TITLE_FIELDS = ("student_name", "guardian_name")


def parse_bool(value: str) -> bool | None:
    text = value.strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    text = text.split(" ")[0].split("T")[0]  # XLSX cells arrive as "2008-03-14 00:00:00"
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


@dataclass
class NormalizedRow:
    """One mapped row. ``values`` holds normalised strings or typed values; ``invalid`` lists
    fields whose value was present but could not be parsed."""

    row_number: int
    values: dict[str, Any] = field(default_factory=dict)
    invalid: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        values = {k: v.isoformat() if isinstance(v, date) else v for k, v in self.values.items()}
        return {"row_number": self.row_number, "values": values, "invalid": self.invalid}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> NormalizedRow:
        values = dict(data["values"])
        for f in DATE_FIELDS:
            if isinstance(values.get(f), str):
                values[f] = date.fromisoformat(values[f])
        return cls(data["row_number"], values, dict(data.get("invalid", {})))


def normalize_row(
    raw: dict[str, str], mapping: dict[str, str], row_number: int, secret: str
) -> NormalizedRow:
    """Apply the mapping and normalise every template column. Contacts come out hashed."""
    row = NormalizedRow(row_number)
    mapped = {target: raw.get(header, "") for header, target in mapping.items()}
    for column in TEMPLATE_COLUMNS:
        value = _collapse(str(mapped.get(column, "") or ""))
        if column in CONTACT_FIELDS:
            kind = "phone" if column == "contact_phone" else "email"
            row.values[column] = hash_contact(value, secret, kind)
        elif not value:
            row.values[column] = None
        elif column in BOOL_FIELDS:
            parsed = parse_bool(value)
            row.values[column] = parsed
            if parsed is None:
                row.invalid[column] = value
        elif column in DATE_FIELDS:
            parsed = parse_date(value)
            row.values[column] = parsed
            if parsed is None:
                row.invalid[column] = value
        elif column == "qualifying_exam_pct":
            try:
                pct = round(float(value), 2)
                row.values[column] = pct if 0 <= pct <= 100 else None
                if row.values[column] is None:
                    row.invalid[column] = value
            except ValueError:
                row.values[column] = None
                row.invalid[column] = value
        elif column in UPPER_FIELDS:
            row.values[column] = value.upper()
        elif column in LOWER_FIELDS:
            row.values[column] = value.lower()
        elif column in TITLE_FIELDS:
            row.values[column] = value.title()
        elif column == "apaar_id":
            row.values[column] = value.replace(" ", "")
        else:
            row.values[column] = value
    return row


def normalize_rows(
    raw_rows: list[dict[str, str]], mapping: dict[str, str], secret: str
) -> list[NormalizedRow]:
    """Row numbers are 1-based data rows (the header is not counted)."""
    return [normalize_row(r, mapping, i, secret) for i, r in enumerate(raw_rows, start=1)]
