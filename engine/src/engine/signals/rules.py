# Owner: Dev A
"""Rule-based integrity signals computed over committed admissions.

This module provides backward-compatible functional wrappers around the modular
signals implemented in engine.signals.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from engine.config import SHARED_CONTACT_THRESHOLD
from engine.signals.backdated import _parse_date, backdated_signal
from engine.signals.eligibility import eligibility_signal
from engine.signals.shared_contacts import shared_contacts_signal
from engine.types import Signal

Row = dict[str, Any]


def eligibility(admissions: list[Row]) -> list[Signal]:
    """Flag admissions whose qualifying percentage breaks programme norms.

    Supports both:
    1. Per-row validation hook form (when rows include 'row_number'):
       Returns Signal objects with code='QUALIFYING_BELOW_NORM', severity='warning',
       and evidence['row_numbers'] containing the affected row_number(s).
    2. Aggregate institution-level signals for /engine/* and scoring.
    """
    if admissions and any("row_number" in r for r in admissions):
        signals: list[Signal] = []
        for r in admissions:
            row_num = r.get("row_number")
            if row_num is None:
                continue
            pct = r.get("qualifying_exam_pct")
            if pct is None or pct == "":
                continue
            try:
                pct_val = float(pct)
            except (ValueError, TypeError):
                continue

            raw_cat = r.get("category")
            cat = raw_cat.strip().lower() if isinstance(raw_cat, str) and raw_cat.strip() else None
            norm = 40.0 if cat in {"obc", "sc", "st", "ews"} else 45.0
            if pct_val < norm:
                display_cat = cat or "general"
                signals.append(
                    Signal(
                        code="QUALIFYING_BELOW_NORM",
                        signal_name="QUALIFYING_BELOW_NORM",
                        severity="warning",
                        institution_id=str(
                            r.get("institution_aicte_code") or r.get("institution_id") or ""
                        ),
                        evidence={
                            "row_numbers": [row_num],
                            "reason": (
                                f"Qualifying percentage {pct_val}% is below AICTE minimum "
                                f"{norm}% for category '{display_cat}'."
                            ),
                            "qualifying_exam_pct": pct_val,
                            "norm": norm,
                            "category": display_cat,
                        },
                        description=(
                            f"Qualifying percentage {pct_val}% is below AICTE norm of {norm}%."
                        ),
                    )
                )
        return signals

    return eligibility_signal(admissions)


def shared_contact_clusters(
    admissions: list[Row], min_size: int = SHARED_CONTACT_THRESHOLD
) -> list[Signal]:
    """Flag clusters of students sharing the same hashed phone or email."""
    return shared_contacts_signal(
        admissions, min_cluster_size=min_size, cross_institution_min=min_size
    )


def backdating(admissions: list[Row]) -> list[Signal]:
    """Flag admissions entered long after their stated admission date.

    Supports both:
    1. Per-row validation hook form (when rows include 'row_number'):
       Returns Signal objects with code='BACKDATED_ENTRY', severity='review',
       and evidence['row_numbers'] containing the affected row_number(s).
    2. Aggregate institution-level signals for /engine/* and scoring.
    """
    if admissions and any("row_number" in r for r in admissions):
        signals: list[Signal] = []
        for r in admissions:
            row_num = r.get("row_number")
            if row_num is None:
                continue

            adm_date_raw = r.get("admission_date")
            upload_date_raw = (
                r.get("upload_date") or r.get("created_at") or r.get("batch_upload_date")
            )
            if not adm_date_raw or not upload_date_raw:
                continue

            adm_date = _parse_date(adm_date_raw)
            upload_date = _parse_date(upload_date_raw)
            if not adm_date or not upload_date:
                continue

            academic_year_raw = r.get("academic_year")
            start_year: int | None = None
            if academic_year_raw and isinstance(academic_year_raw, str):
                import re

                m = re.match(r"^(\d{4})", academic_year_raw.strip())
                if m:
                    start_year = int(m.group(1))

            if start_year is None and upload_date:
                start_year = upload_date.year
            if start_year is None:
                start_year = adm_date.year

            # In AICTE admissions (and datagen's anomaly catalogue), regular admissions
            # occur in July–September (window opens July 1). Backdated entries are planted
            # by moving admission date to March–May (months before the window), or entered
            # from prior years. Clean institutions submit admissions after the window closes
            # (July–September admissions uploaded in October), which is normal.
            window_start = date(start_year, 7, 1)
            is_backdated = False
            reason = ""

            if adm_date < window_start:
                is_backdated = True
                reason = (
                    f"Admission date {adm_date.isoformat()} is before the July–September "
                    f"admission window for academic year {start_year}."
                )
            elif (upload_date - adm_date).days > 180:
                delay = (upload_date - adm_date).days
                is_backdated = True
                reason = f"Admission entered with excessive delay ({delay} days) before upload."

            if is_backdated:
                delay = (upload_date - adm_date).days
                signals.append(
                    Signal(
                        code="BACKDATED_ENTRY",
                        signal_name="BACKDATED_ENTRY",
                        severity="review",
                        institution_id=str(
                            r.get("institution_aicte_code") or r.get("institution_id") or ""
                        ),
                        evidence={
                            "row_numbers": [row_num],
                            "reason": reason,
                            "delay": delay,
                            "admission_date": adm_date.isoformat(),
                        },
                        description=reason,
                    )
                )
        return signals

    return backdated_signal(admissions)


def cap_filling(admissions: list[Row], seat_pools: list[Row]) -> list[Signal]:
    """Flag pools filled beyond approved intake."""
    return eligibility_signal(admissions, seat_pools=seat_pools)


intake_overrun = cap_filling
