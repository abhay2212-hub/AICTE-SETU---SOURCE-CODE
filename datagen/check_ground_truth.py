# Owner: Dev C
"""Read-only validation for a generated datagen output directory.

Usage:
    uv run python check_ground_truth.py [DATASET_DIR]

The default DATASET_DIR is ``out`` beside this file.  This script never
creates, modifies, or deletes dataset files.
"""

from __future__ import annotations

import argparse
import ast
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


REQUIRED_TRUTH_COLUMNS = ("record_id", "anomaly_type", "details")
REQUIRED_ADMISSION_COLUMNS = (
    "institution_aicte_code",
    "programme_code",
    "academic_year",
    "seat_pool",
)
REQUIRED_INTAKE_COLUMNS = (*REQUIRED_ADMISSION_COLUMNS, "approved_seats")
REQUIRED_DEMO_COLUMNS = (
    "institution_aicte_code",
    "programme_code",
    "academic_year",
    "student_name",
    "dob",
    "gender",
    "category",
    "pwd",
    "apaar_id",
    "apaar_opt_out",
    "provisional_id",
    "nationality",
    "oci_status",
    "fn_status",
    "nri_category",
    "seat_pool",
    "admission_mode",
    "admission_date",
    "qualifying_exam",
    "qualifying_exam_pct",
    "domicile_state",
    "contact_phone",
    "contact_email",
    "guardian_name",
)
KNOWN_ANOMALIES = {
    "intake_overrun",
    "dup_cross_institution",
    "typo_duplicate",
    "shared_contact_cluster",
    "backdated_entry",
    "opted_out",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV without changing it."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def pool_key(row: dict[str, str]) -> str:
    return "|".join(row[column].strip() for column in REQUIRED_ADMISSION_COLUMNS)


def required_columns_present(columns: list[str], required: tuple[str, ...], name: str) -> bool:
    missing = [column for column in required if column not in columns]
    if missing:
        print(f"FAIL {name}: missing required columns: {', '.join(missing)}")
        return False
    print(f"PASS {name}: required columns present")
    return True


def literal_assignment(path: Path, name: str) -> object | None:
    """Read one literal assignment without importing or executing its module."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def check_scripted_demo_fixtures(repo_root: Path) -> bool:
    """Validate the source-controlled demo fixtures without executing backend code."""
    ok = True
    loader_path = repo_root / "backend" / "scripts" / "load_demo.py"
    live_csv_path = repo_root / "deck" / "demo" / "shadow-late-batch.csv"

    story = literal_assignment(loader_path, "SHADOW_STORY") if loader_path.is_file() else None
    if not isinstance(story, dict):
        print(f"FAIL fixture Shadow source: cannot read literal SHADOW_STORY from {loader_path}")
        ok = False
    else:
        expected_story = {"admitted": 71, "approved": 60, "overrun_by": 11}
        mismatches = [
            f"{key}={story.get(key)!r} (expected {value!r})"
            for key, value in expected_story.items()
            if story.get(key) != value
        ]
        if mismatches:
            print(f"FAIL fixture Shadow Institute 71/60 overrun: {', '.join(mismatches)}")
            ok = False
        else:
            print("PASS fixture Shadow Institute 71/60 overrun: scripted source values match")

        if story.get("blind_match_with_narmada") == 1:
            print("PASS fixture Shadow-Narmada Blind Match: scripted source count is 1")
        else:
            print(
                "FAIL fixture Shadow-Narmada Blind Match: "
                f"blind_match_with_narmada={story.get('blind_match_with_narmada')!r} (expected 1)"
            )
            ok = False

    if not live_csv_path.is_file():
        print(f"FAIL fixture live Shadow upload: missing: {live_csv_path}")
        return False

    demo_columns, demo_rows = read_csv(live_csv_path)
    if not required_columns_present(demo_columns, REQUIRED_DEMO_COLUMNS, "shadow-late-batch.csv"):
        ok = False
    if len(demo_rows) != 3:
        print(f"FAIL fixture live Shadow upload: expected 3 rows, found {len(demo_rows)}")
        ok = False
    else:
        print("PASS fixture live Shadow upload: contains 3 rows")

    required_values = [
        f"row {index} ({column})"
        for index, row in enumerate(demo_rows, start=2)
        for column in REQUIRED_DEMO_COLUMNS
        if column != "provisional_id" and not (row.get(column) or "").strip()
    ]
    if required_values:
        print(f"FAIL fixture live Shadow upload: empty required values: {', '.join(required_values[:10])}")
        ok = False
    else:
        print("PASS fixture live Shadow upload: all required values are populated")

    expected_upload = {
        "institution_aicte_code": "1-9999003",
        "programme_code": "UG-CSE",
        "academic_year": "2026-27",
        "seat_pool": "regular",
    }
    content_mismatches = [
        f"row {index}"
        for index, row in enumerate(demo_rows, start=2)
        if any(row.get(column) != value for column, value in expected_upload.items())
    ]
    if content_mismatches:
        print(f"FAIL fixture live Shadow upload: unexpected batch values in {', '.join(content_mismatches)}")
        ok = False
    else:
        print("PASS fixture live Shadow upload: Shadow UG-CSE 2026-27 regular rows match")

    typo_rows = [row for row in demo_rows if row.get("student_name") == "Yash Tiwarii"]
    if len(typo_rows) == 1 and typo_rows[0].get("apaar_opt_out") == "false":
        print("PASS fixture live Shadow upload: contains the labelled Blind Match typo row")
    else:
        print("FAIL fixture live Shadow upload: expected one non-opt-out Yash Tiwarii typo row")
        ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset_dir",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parent / "out",
        help="directory containing generated CSVs (default: datagen/out)",
    )
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    truth_path = dataset_dir / "ground_truth.csv"
    fixture_ok = check_scripted_demo_fixtures(Path(__file__).resolve().parent.parent)

    print(f"Dataset directory: {dataset_dir}")
    print("Read-only checker: no files will be modified.")

    if not truth_path.is_file():
        print(f"FAIL ground_truth.csv: missing: {truth_path}")
        print("NOT RUN: generated-data columns, row count, anomaly counts, and data-quality checks")
        print("Reason: ground_truth.csv is required; the checker will not generate it.")
        print("SUMMARY: FAIL")
        return 1

    truth_columns, truth_rows = read_csv(truth_path)
    dataset_format_ok = required_columns_present(
        truth_columns, REQUIRED_TRUTH_COLUMNS, "ground_truth.csv"
    )
    ok = fixture_ok and dataset_format_ok
    if not dataset_format_ok:
        print("NOT RUN: dataset-dependent checks require the ground-truth columns above.")
        print("SUMMARY: FAIL")
        return 1

    print(f"PASS ground_truth.csv: {len(truth_rows)} rows")
    anomaly_counts = Counter(row["anomaly_type"].strip() for row in truth_rows)
    print("Anomaly counts:")
    for anomaly, count in sorted(anomaly_counts.items()):
        print(f"  {anomaly}: {count}")

    unknown = sorted(set(anomaly_counts) - KNOWN_ANOMALIES)
    if unknown:
        print(f"FAIL ground_truth.csv: unknown anomaly types: {', '.join(unknown)}")
        ok = False
    else:
        print("PASS ground_truth.csv: all anomaly types are known")

    blank_truth = [
        f"row {index} ({column})"
        for index, row in enumerate(truth_rows, start=2)
        for column in REQUIRED_TRUTH_COLUMNS
        if not (row.get(column) or "").strip()
    ]
    if blank_truth:
        print(f"FAIL ground_truth.csv: empty required values: {', '.join(blank_truth[:10])}")
        ok = False
    else:
        print("PASS ground_truth.csv: no empty required values")

    duplicate_labels = [
        label
        for label, count in Counter(
            (row["record_id"].strip(), row["anomaly_type"].strip()) for row in truth_rows
        ).items()
        if count > 1
    ]
    if duplicate_labels:
        print(f"FAIL ground_truth.csv: duplicate record_id/anomaly_type labels: {duplicate_labels[:10]}")
        ok = False
    else:
        print("PASS ground_truth.csv: no duplicate record_id/anomaly_type labels")

    admissions_path = dataset_dir / "admissions.csv"
    intake_path = dataset_dir / "intake.csv"
    institutions_path = dataset_dir / "institutions.csv"
    missing_data = [
        path.name for path in (admissions_path, intake_path, institutions_path) if not path.is_file()
    ]
    if missing_data:
        print(f"NOT RUN: referential, fixture, and admission empty-value checks; missing: {', '.join(missing_data)}")
        print("SUMMARY: FAIL")
        return 1

    admission_columns, admissions = read_csv(admissions_path)
    intake_columns, intake = read_csv(intake_path)
    institution_columns, institutions = read_csv(institutions_path)
    format_ok = (
        required_columns_present(admission_columns, REQUIRED_ADMISSION_COLUMNS, "admissions.csv")
        and required_columns_present(intake_columns, REQUIRED_INTAKE_COLUMNS, "intake.csv")
        and required_columns_present(institution_columns, ("aicte_code",), "institutions.csv")
    )
    if not format_ok:
        print("NOT RUN: referential and fixture checks require the columns above.")
        print("SUMMARY: FAIL")
        return 1

    record_ids = {f"R{index:07d}" for index in range(1, len(admissions) + 1)}
    institutions_by_code = {row["aicte_code"].strip() for row in institutions}
    admission_institutions = {row["institution_aicte_code"].strip() for row in admissions}
    intake_by_pool = {pool_key(row): row for row in intake}
    admissions_by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in admissions:
        admissions_by_pool[pool_key(row)].append(row)

    duplicate_institution_ids = [
        code for code, count in Counter(row["aicte_code"].strip() for row in institutions).items() if count > 1
    ]
    if duplicate_institution_ids:
        print(f"FAIL institutions.csv: duplicate aicte_code values: {duplicate_institution_ids[:10]}")
        ok = False
    else:
        print("PASS institutions.csv: no duplicate aicte_code values")

    missing_institutions = sorted(admission_institutions - institutions_by_code)
    if missing_institutions:
        print(f"FAIL admissions.csv: institutions not in institutions.csv: {missing_institutions[:10]}")
        ok = False
    else:
        print("PASS admissions.csv: all institutions exist in institutions.csv")

    row_label_targets = [row["record_id"].strip() for row in truth_rows if "|" not in row["record_id"]]
    missing_record_targets = sorted(set(row_label_targets) - record_ids)
    if missing_record_targets:
        print(f"FAIL ground_truth.csv: labels point to missing admission rows: {missing_record_targets[:10]}")
        ok = False
    else:
        print("PASS ground_truth.csv: all row labels point to admission rows")

    overrun_labels = [row for row in truth_rows if row["anomaly_type"].strip() == "intake_overrun"]
    invalid_overruns: list[str] = []
    for label in overrun_labels:
        key = label["record_id"].strip()
        intake_row = intake_by_pool.get(key)
        if intake_row is None:
            invalid_overruns.append(f"{key} (pool not in intake.csv)")
            continue
        try:
            approved = int(intake_row["approved_seats"])
        except ValueError:
            invalid_overruns.append(f"{key} (invalid approved_seats)")
            continue
        if len(admissions_by_pool[key]) <= approved:
            invalid_overruns.append(f"{key} (not over capacity)")
    if invalid_overruns:
        print(f"FAIL intake_overrun labels: {invalid_overruns[:10]}")
        ok = False
    else:
        print("PASS intake_overrun labels: every labelled pool exists and exceeds approved seats")

    empty_admission_values = [
        f"row {index} ({column})"
        for index, row in enumerate(admissions, start=2)
        for column in REQUIRED_ADMISSION_COLUMNS
        if not row[column].strip()
    ]
    if empty_admission_values:
        print(f"FAIL admissions.csv: empty identity/pool values: {', '.join(empty_admission_values[:10])}")
        ok = False
    else:
        print("PASS admissions.csv: no empty identity/pool values")

    apaar_institutions: dict[str, set[str]] = defaultdict(set)
    for row in admissions:
        apaar = row.get("apaar_id", "").strip()
        if apaar:
            apaar_institutions[apaar].add(row["institution_aicte_code"].strip())
    exact_pairs = [apaar for apaar, codes in apaar_institutions.items() if len(codes) > 1]
    blind_labels = [
        row for row in truth_rows if row["anomaly_type"].strip() in {"dup_cross_institution", "typo_duplicate"}
    ]
    if blind_labels and exact_pairs:
        print("PASS generated Blind Match data: duplicate labels and a cross-institution APAAR pair found")
    else:
        print("FAIL generated Blind Match data: expected duplicate labels and cross-institution APAAR pair not found")
        ok = False

    if overrun_labels:
        print("PASS generated overrun data: labelled intake-overrun pool(s) found")
    else:
        print("FAIL generated overrun data: no intake_overrun label found")
        ok = False

    print(f"SUMMARY: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
