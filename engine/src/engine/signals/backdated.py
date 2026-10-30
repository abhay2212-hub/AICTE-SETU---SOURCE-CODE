# Owner: Dev A
"""Signal detecting admissions entered significantly later than their stated admission date."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from engine.signals.base import SignalSeverity
from engine.types import Signal

Row = dict[str, Any]


def _parse_date(val: Any) -> date | None:
    """Safely parse a date from date, datetime, or string."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    match_ymd = re.search(r"\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if match_ymd:
        try:
            return date(int(match_ymd.group(1)), int(match_ymd.group(2)), int(match_ymd.group(3)))
        except ValueError:
            return None
    match_dmy = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", s)
    if match_dmy:
        try:
            return date(int(match_dmy.group(3)), int(match_dmy.group(2)), int(match_dmy.group(1)))
        except ValueError:
            return None
    return None


def backdated_signal(
    admissions: list[Row],
    max_delay_days: int = 30,
    reference_upload_date: date | datetime | None = None,
) -> list[Signal]:
    """Detect admissions entered significantly later than the admission date.

    Pure function returning structured evidence with:
    - admission date
    - upload date
    - delay (in days)
    - student id
    """
    if not admissions:
        return []

    default_upload = (
        reference_upload_date.date()
        if isinstance(reference_upload_date, datetime)
        else reference_upload_date
    )

    by_inst: dict[str, list[dict[str, Any]]] = {}

    for row in admissions:
        if not isinstance(row, dict):
            continue
        inst_id = str(row.get("institution_id") or "unknown")
        student_id = str(row.get("student_id") or row.get("id") or "unknown")

        adm_date = _parse_date(row.get("admission_date"))
        upload_date = (
            _parse_date(row.get("upload_date"))
            or _parse_date(row.get("created_at"))
            or _parse_date(row.get("batch_upload_date"))
            or default_upload
        )

        if not adm_date or not upload_date:
            continue

        delay = (upload_date - adm_date).days
        if delay > max_delay_days:
            by_inst.setdefault(inst_id, []).append(
                {
                    "student_id": student_id,
                    "admission_date": adm_date.isoformat(),
                    "upload_date": upload_date.isoformat(),
                    "delay": delay,
                }
            )

    signals: list[Signal] = []

    for inst_id, flagged in by_inst.items():
        count = len(flagged)
        max_delay = max(item["delay"] for item in flagged)
        first_item = flagged[0]

        # Scale severity based on delay and count
        importance = "critical" if max_delay >= 90 or count >= 10 else "high"
        severity = SignalSeverity.calculate(importance, affected_count=count)
        score = min(100.0, 60.0 + min(count, 10) * 2.5 + min(max_delay, 60) * 0.25)

        evidence: dict[str, Any] = {
            "student_id": (
                first_item["student_id"]
                if count == 1
                else ", ".join(item["student_id"] for item in flagged[:5])
            ),
            "institution_id": inst_id,
            "admission_date": first_item["admission_date"],
            "upload_date": first_item["upload_date"],
            "delay": first_item["delay"],
            "reason": (
                f"{count} admission(s) entered with delay exceeding {max_delay_days} days "
                f"(max delay: {max_delay} days)."
            ),
            "backdated_count": count,
            "threshold_days": max_delay_days,
            "max_delay_days": max_delay,
            "admissions": flagged,
            "details": {
                "admission_date": first_item["admission_date"],
                "upload_date": first_item["upload_date"],
                "delay": first_item["delay"],
                "threshold_days": max_delay_days,
                "max_delay_days": max_delay,
                "backdated_count": count,
                "admissions": flagged,
            },
        }

        signals.append(
            Signal(
                signal_id=str(uuid4()),
                institution_id=inst_id,
                signal_name="BACKDATED_ADMISSIONS",
                severity=severity,
                score=round(score, 1),
                evidence=evidence,
                description=(
                    f"Institution entered {count} admission(s) with excessive delay "
                    f"(up to {max_delay} days) beyond the {max_delay_days}-day threshold."
                ),
                created_at=datetime.now(UTC),
            )
        )

    return signals
