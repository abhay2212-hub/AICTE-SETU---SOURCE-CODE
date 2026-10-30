# Owner: Dev A
"""Signal detecting student and institution admission eligibility violations against APH norms."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from engine.signals.base import SignalSeverity
from engine.types import Signal

Row = dict[str, Any]

DEFAULT_CONFIG: dict[str, Any] = {
    "min_pct_general": 45.0,
    "min_pct_reserved": 40.0,
    "reserved_categories": {"obc", "sc", "st", "ews"},
    "valid_categories": {"general", "ews", "obc", "sc", "st"},
    "valid_seat_pools": {"regular", "tfw", "fn_oci_pio", "nri"},
    "min_age": 15,
    "max_age": 60,
    "default_approved_intake": 60,
}


def _parse_date(val: Any) -> date | None:
    """Safely parse a date from date, datetime, or string."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    # Match YYYY-MM-DD or YYYY/MM/DD
    match = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    # Match DD-MM-YYYY or DD/MM/YYYY
    match_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", s)
    if match_dmy:
        try:
            return date(int(match_dmy.group(3)), int(match_dmy.group(2)), int(match_dmy.group(1)))
        except ValueError:
            return None
    return None


def _calculate_age(dob_val: Any, admission_date_val: Any) -> int | None:
    """Derive student age at time of admission."""
    try:
        dob = _parse_date(dob_val)
        if not dob:
            return None

        adm_date = _parse_date(admission_date_val) or date.today()
        return adm_date.year - dob.year - ((adm_date.month, adm_date.day) < (dob.month, dob.day))
    except Exception:
        return None


def eligibility_signal(
    admissions: list[Row],
    rules_config: dict[str, Any] | None = None,
    seat_pools: list[Row] | None = None,
) -> list[Signal]:
    """Detect admissions violating configurable AICTE Approval Process Handbook (APH) rules.

    Pure function returning structured evidence for:
    - Qualifying exam percentage below norms
    - Invalid admission category
    - Invalid quota / seat pool
    - Exceeded approved intake
    - Implausible age at admission
    - Invalid programme eligibility
    """
    cfg = {**DEFAULT_CONFIG, **(rules_config or {})}

    # Build approved intake map: (institution_id, programme_code) -> approved seats
    # Build approved intake map: (institution_id, programme_code) -> approved seats
    # and pool-level intake map if pool details are provided
    intake_map: dict[tuple[str, str], int] = {}
    pool_intake_map: dict[tuple[str, str, str, str], int] = {}
    if seat_pools:
        for pool in seat_pools:
            if not isinstance(pool, dict):
                continue
            inst = str(pool.get("institution_id") or pool.get("institution_aicte_code") or "")
            prog = str(pool.get("programme_code", ""))
            seats = int(pool.get("approved_seats", cfg["default_approved_intake"]))
            intake_map[(inst, prog)] = intake_map.get((inst, prog), 0) + seats

            pool_name = str(pool.get("seat_pool") or pool.get("pool") or "").strip().lower()
            year = str(pool.get("academic_year") or "").strip()
            if pool_name and year:
                pool_intake_map[(inst, prog, year, pool_name)] = seats

    # Group admissions and violations per institution
    inst_admissions_count: dict[tuple[str, str], int] = {}
    pool_admissions_count: dict[tuple[str, str, str, str], int] = {}
    violations_by_inst: dict[str, list[dict[str, Any]]] = {}

    for row in admissions:
        if not isinstance(row, dict):
            continue
        inst_id = str(row.get("institution_id") or "unknown")
        student_id = str(row.get("student_id") or row.get("id") or "unknown")
        prog = str(row.get("programme_code") or row.get("programme_id") or "UNKNOWN")

        # Track intake counts
        key = (inst_id, prog)
        inst_admissions_count[key] = inst_admissions_count.get(key, 0) + 1

        # Track pool-level intake counts if seat_pool and academic_year are present
        p_name = str(row.get("seat_pool") or row.get("quota") or "").strip().lower()
        acad_year = str(row.get("academic_year") or "").strip()
        if p_name and acad_year:
            p_key = (inst_id, prog, acad_year, p_name)
            pool_admissions_count[p_key] = pool_admissions_count.get(p_key, 0) + 1

        # 1. Qualifying Exam Percentage
        pct = row.get("qualifying_exam_pct")
        cat_raw = row.get("category")
        cat = cat_raw.strip().lower() if isinstance(cat_raw, str) and cat_raw.strip() else None
        if pct is not None:
            try:
                pct_float = float(pct)
                req_pct = (
                    cfg["min_pct_reserved"]
                    if cat and cat in cfg["reserved_categories"]
                    else cfg["min_pct_general"]
                )
                prog_req = cfg.get("programme_min_pct", {}).get(prog)
                if prog_req is not None:
                    req_pct = max(req_pct, float(prog_req))

                if pct_float < req_pct:
                    display_cat = cat or "general"
                    violations_by_inst.setdefault(inst_id, []).append(
                        {
                            "violated_rule": "QUALIFYING_BELOW_NORM",
                            "student_id": student_id,
                            "programme": prog,
                            "expected_value": f">= {req_pct}%",
                            "actual_value": f"{pct_float}%",
                            "reason": (
                                f"Qualifying percentage {pct_float}% is below "
                                f"AICTE minimum {req_pct}% for category '{display_cat}'"
                            ),
                        }
                    )
            except (ValueError, TypeError):
                pass

        # 2. Admission Category Validation
        if cat is not None and cat not in cfg["valid_categories"]:
            violations_by_inst.setdefault(inst_id, []).append(
                {
                    "violated_rule": "INVALID_CATEGORY",
                    "student_id": student_id,
                    "programme": prog,
                    "expected_value": f"One of {sorted(cfg['valid_categories'])}",
                    "actual_value": cat,
                    "reason": f"Admission category '{cat}' is not recognized under AICTE norms",
                }
            )

        # 3. Quota / Seat Pool Validation
        pool_name = str(row.get("seat_pool") or row.get("quota") or "").strip().lower()
        valid_pools = cfg.get("valid_seat_pools", DEFAULT_CONFIG["valid_seat_pools"])
        if pool_name and pool_name not in valid_pools:
            violations_by_inst.setdefault(inst_id, []).append(
                {
                    "violated_rule": "INVALID_QUOTA",
                    "student_id": student_id,
                    "programme": prog,
                    "expected_value": f"One of {sorted(valid_pools)}",
                    "actual_value": pool_name,
                    "reason": f"Seat pool '{pool_name}' is not an approved AICTE seat pool",
                }
            )

        # 4. Implausible Age Validation
        dob_val = row.get("dob") or row.get("date_of_birth")
        adm_date_val = row.get("admission_date")
        age = _calculate_age(dob_val, adm_date_val)
        if age is not None:
            if age < cfg["min_age"] or age > cfg["max_age"]:
                violations_by_inst.setdefault(inst_id, []).append(
                    {
                        "violated_rule": "AGE_IMPLAUSIBLE",
                        "student_id": student_id,
                        "programme": prog,
                        "expected_value": f"Between {cfg['min_age']} and {cfg['max_age']} years",
                        "actual_value": f"{age} years",
                        "reason": (
                            f"Age {age} at admission is outside plausible "
                            f"range ({cfg['min_age']}-{cfg['max_age']})"
                        ),
                    }
                )

        # 5. Programme Eligibility Validation
        valid_programmes = cfg.get("valid_programmes")
        if valid_programmes and prog not in valid_programmes:
            violations_by_inst.setdefault(inst_id, []).append(
                {
                    "violated_rule": "INVALID_PROGRAMME_ELIGIBILITY",
                    "student_id": student_id,
                    "programme": prog,
                    "expected_value": f"One of {sorted(valid_programmes)}",
                    "actual_value": prog,
                    "reason": (
                        f"Programme '{prog}' is not an approved eligible programme under APH norms"
                    ),
                }
            )

    # 6. Exceeded Approved Intake Check
    if pool_intake_map:
        for (inst_id, prog, year, p_name), count in pool_admissions_count.items():
            approved = pool_intake_map.get((inst_id, prog, year, p_name))
            if approved is not None and count > approved:
                pool_str = f"{inst_id}|{prog}|{year}|{p_name}"
                violations_by_inst.setdefault(inst_id, []).append(
                    {
                        "violated_rule": "EXCEEDED_INTAKE",
                        "student_id": pool_str,
                        "pool_key": pool_str,
                        "programme": prog,
                        "seat_pool": p_name,
                        "academic_year": year,
                        "expected_value": f"<= {approved} seats",
                        "actual_value": f"{count} admitted",
                        "reason": (
                            f"Pool '{p_name}' admitted ({count}) exceeds "
                            f"approved capacity of {approved} seats"
                        ),
                    }
                )
    else:
        for (inst_id, prog), count in inst_admissions_count.items():
            approved = intake_map.get((inst_id, prog), cfg.get(f"intake_{prog}"))
            if approved and count > approved:
                violations_by_inst.setdefault(inst_id, []).append(
                    {
                        "violated_rule": "EXCEEDED_INTAKE",
                        "student_id": "INSTITUTION_BATCH",
                        "programme": prog,
                        "expected_value": f"<= {approved} seats",
                        "actual_value": f"{count} admitted",
                        "reason": (
                            f"Total admitted ({count}) exceeds approved "
                            f"capacity of {approved} seats"
                        ),
                    }
                )

    # Generate Signal objects
    signals: list[Signal] = []
    for inst_id, violations in violations_by_inst.items():
        count = len(violations)
        severity = SignalSeverity.calculate("high", affected_count=count)
        score = min(100.0, 70.0 + count * 5.0)

        first_v = violations[0] if violations else {}
        evidence: dict[str, Any] = {
            "institution_id": inst_id,
            "student_id": (
                first_v.get("student_id", "unknown")
                if count == 1
                else ", ".join(v.get("student_id", "") for v in violations[:5])
            ),
            "violated_rule": (
                first_v.get("violated_rule", "MULTIPLE_RULES") if count == 1 else "MULTIPLE_RULES"
            ),
            "programme": (first_v.get("programme", "MULTIPLE") if count == 1 else "MULTIPLE"),
            "expected_value": first_v.get("expected_value", "") if count == 1 else "",
            "actual_value": first_v.get("actual_value", "") if count == 1 else "",
            "reason": (
                f"{count} admission eligibility violation(s) detected under AICTE APH norms."
            ),
            "violations_count": count,
            "violations": violations,
            "details": {
                "violations_count": count,
                "violations": violations,
            },
        }

        signals.append(
            Signal(
                signal_id=str(uuid4()),
                institution_id=inst_id,
                signal_name="ELIGIBILITY_VIOLATION",
                severity=severity,
                score=round(score, 1),
                evidence=evidence,
                description=(
                    f"Institution has {count} student admission(s) violating "
                    "AICTE APH eligibility rules."
                ),
                created_at=datetime.now(UTC),
            )
        )

    return signals
