# Owner: Dev C
"""Pure pandas aggregations for the reports data layer.

Inputs are pre-joined DataFrames: one row per admission, with programme and
institution attributes already attached.  These functions do not query a
database, read files, or mutate their inputs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import pandas as pd

EnrolmentGroup = Literal["state", "programme", "category", "gender"]
_ENROLMENT_COLUMNS = ("state", "programme_code", "category", "gender", "opted_out")
_INTAKE_COLUMNS = ("programme_id", "programme_code", "pool", "approved_seats", "rule_version")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {', '.join(missing)}")


def _active(frame: pd.DataFrame) -> pd.DataFrame:
    """Return active admissions when an ``active`` marker is available."""
    if "active" not in frame.columns:
        return frame.copy()
    return frame.loc[frame["active"].fillna(False).astype(bool)].copy()


def enrolment_rows(admissions: pd.DataFrame, group_by: EnrolmentGroup) -> pd.DataFrame:
    """Count active admissions and APAAR opt-outs by one contract-supported group.

    Missing grouping values are represented as ``<unknown>`` so records are not
    silently dropped from a report.
    """
    _require_columns(admissions, _ENROLMENT_COLUMNS, "admissions")
    column_by_group = {
        "state": "state",
        "programme": "programme_code",
        "category": "category",
        "gender": "gender",
    }
    if group_by not in column_by_group:
        raise ValueError(f"Unsupported enrolment grouping: {group_by}")

    group_column = column_by_group[group_by]
    rows = _active(admissions)
    if rows.empty:
        return pd.DataFrame(columns=["group", "admissions", "opted_out"])

    rows["group"] = rows[group_column].fillna("<unknown>").astype(str).str.strip()
    rows.loc[rows["group"] == "", "group"] = "<unknown>"
    rows["_opted_out"] = rows["opted_out"].fillna(False).astype(bool).astype(int)
    result = (
        rows.groupby("group", as_index=False, sort=True)
        .agg(admissions=("group", "size"), opted_out=("_opted_out", "sum"))
        .astype({"admissions": "int64", "opted_out": "int64"})
    )
    return result


def latest_intake(intake: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest lexical rule version for each ``(programme_id, pool)``.

    This deliberately mirrors the existing seat-ledger SQL ordering by
    ``rule_version desc``.  The returned DataFrame has at most one row for each
    programme/pool and is safe to sum without double-counting superseded rules.
    """
    _require_columns(intake, _INTAKE_COLUMNS, "intake")
    if intake.empty:
        return intake.copy()
    rows = intake.copy()
    rows["rule_version"] = rows["rule_version"].fillna("").astype(str)
    rows["approved_seats"] = pd.to_numeric(rows["approved_seats"], errors="coerce").fillna(0)
    rows = rows.sort_values(
        ["programme_id", "pool", "rule_version"],
        ascending=[True, True, False],
        kind="stable",
    )
    return rows.drop_duplicates(["programme_id", "pool"], keep="first").reset_index(drop=True)


def programme_utilisation_rows(admissions: pd.DataFrame, intake: pd.DataFrame) -> pd.DataFrame:
    """Return admitted/approved utilisation by programme.

    ``utilisation`` is a ratio, not a percentage.  It is ``None`` where approved
    intake is zero, avoiding an invented value or division by zero.
    """
    _require_columns(admissions, ("programme_id", "programme_code"), "admissions")
    latest = latest_intake(intake)
    active = _active(admissions)

    admitted = (
        active.groupby(["programme_id", "programme_code"], as_index=False, dropna=False)
        .size()
        .rename(columns={"size": "admitted"})
    )
    approved = latest.groupby("programme_id", as_index=False)["approved_seats"].sum()
    codes = pd.concat(
        [
            admissions[["programme_id", "programme_code"]],
            latest[["programme_id", "programme_code"]],
        ],
        ignore_index=True,
    ).drop_duplicates("programme_id")
    result = codes.merge(admitted, on=["programme_id", "programme_code"], how="left").merge(
        approved, on="programme_id", how="left"
    )
    result["admitted"] = result["admitted"].fillna(0).astype(int)
    result["approved_seats"] = result["approved_seats"].fillna(0).astype(int)
    result["utilisation"] = pd.Series(
        [
            None if row.approved_seats == 0 else row.admitted / row.approved_seats
            for row in result.itertuples(index=False)
        ],
        index=result.index,
        dtype="object",
    )
    return result.sort_values("programme_code", kind="stable").reset_index(drop=True)


def category_admission_rows(admissions: pd.DataFrame) -> pd.DataFrame:
    """Return category-level admitted counts, without a utilisation denominator.

    Seat pools are not categorised in the current schema.  Reporting a category
    utilisation ratio would therefore invent a category-specific approved intake.
    """
    _require_columns(admissions, ("category",), "admissions")
    rows = _active(admissions)
    if rows.empty:
        return pd.DataFrame(columns=["category", "admitted"])
    rows["category"] = rows["category"].fillna("<unknown>").astype(str).str.strip()
    rows.loc[rows["category"] == "", "category"] = "<unknown>"
    return (
        rows.groupby("category", as_index=False, sort=True)
        .size()
        .rename(columns={"size": "admitted"})
        .astype({"admitted": "int64"})
    )


def accreditation_programmes(admissions: pd.DataFrame, intake: pd.DataFrame) -> pd.DataFrame:
    """Return existing-contract programme totals: approved, admitted, and overrun."""
    utilisation = programme_utilisation_rows(admissions, intake)
    result = utilisation.rename(
        columns={"approved_seats": "approved_total", "admitted": "admitted_total"}
    )[["programme_code", "approved_total", "admitted_total"]]
    result["overrun"] = (result["admitted_total"] - result["approved_total"]).clip(lower=0)
    return result.astype({"approved_total": "int64", "admitted_total": "int64", "overrun": "int64"})


def accreditation_report(
    institution: Mapping[str, Any],
    admissions: pd.DataFrame,
    intake: pd.DataFrame,
    *,
    academic_year: str,
    integrity_score: float | None,
    apaar_coverage_pct: float,
    open_review_cases: int,
    integrity_note: str | None = None,
) -> dict[str, Any]:
    """Compose the current ``AccreditationReport`` contract from supplied values.

    Integrity score, APAAR coverage, and open cases are explicit inputs because
    their source and policy belong to the database/query layer, not aggregation.
    ``integrity_score`` is ``None`` until one has been computed; ``integrity_note``
    then says so.
    """
    for key in ("institution_id", "institution_name"):
        if not institution.get(key):
            raise ValueError(f"institution is missing required value: {key}")
    return {
        "institution_id": str(institution["institution_id"]),
        "institution_name": str(institution["institution_name"]),
        "academic_year": academic_year,
        "integrity_score": None if integrity_score is None else float(integrity_score),
        "integrity_note": integrity_note,
        "apaar_coverage_pct": float(apaar_coverage_pct),
        "open_review_cases": int(open_review_cases),
        "programmes": accreditation_programmes(admissions, intake).to_dict("records"),
    }
