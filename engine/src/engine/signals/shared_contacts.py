# Owner: Dev A
"""Signal detecting suspicious sharing of phones, emails, and guardian contacts."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from engine.signals.base import SignalSeverity
from engine.types import Signal

Row = dict[str, Any]


def _normalize_phone(phone: Any) -> str | None:
    """Normalize phone to standardized digits."""
    if not phone:
        return None
    digits = re.sub(r"\D", "", str(phone))
    if len(digits) >= 10:
        return digits[-10:]
    if len(digits) >= 7:
        return digits
    return None


def _normalize_email(email: Any) -> str | None:
    """Normalize email to lowercase stripped string."""
    if not email:
        return None
    clean = str(email).strip().lower()
    if "@" in clean and "." in clean:
        return clean
    return None


def shared_contacts_signal(
    admissions: list[Row],
    min_cluster_size: int = 3,
    cross_institution_min: int = 2,
) -> list[Signal]:
    """Detect suspicious sharing of contact phone, guardian phone, or email across institutions.

    Pure function returning structured evidence with:
    - cluster size
    - affected institutions
    - repeated values
    - grouped student IDs
    """
    if not admissions:
        return []

    # Key: (contact_type, normalized_value) -> {"students": set(), "institutions": set(), ...}
    clusters: dict[tuple[str, str], dict[str, Any]] = {}

    for row in admissions:
        if not isinstance(row, dict):
            continue
        student_id = str(row.get("student_id") or row.get("id") or "unknown")
        inst_id = str(row.get("institution_id") or "unknown")

        # 1. Student Phone
        p1 = _normalize_phone(row.get("contact_phone") or row.get("phone") or row.get("mobile"))
        if p1:
            key = ("phone", p1)
            clusters.setdefault(
                key,
                {"contact_type": "phone", "value": p1, "students": set(), "institutions": set()},
            )
            clusters[key]["students"].add(student_id)
            clusters[key]["institutions"].add(inst_id)

        # 2. Guardian Phone
        p2 = _normalize_phone(row.get("guardian_phone") or row.get("guardian_contact"))
        if p2:
            key = ("guardian_phone", p2)
            clusters.setdefault(
                key,
                {
                    "contact_type": "guardian_phone",
                    "value": p2,
                    "students": set(),
                    "institutions": set(),
                },
            )
            clusters[key]["students"].add(student_id)
            clusters[key]["institutions"].add(inst_id)

        # 3. Email
        em = _normalize_email(row.get("contact_email") or row.get("email"))
        if em:
            key = ("email", em)
            clusters.setdefault(
                key,
                {"contact_type": "email", "value": em, "students": set(), "institutions": set()},
            )
            clusters[key]["students"].add(student_id)
            clusters[key]["institutions"].add(inst_id)

        # 4. Hashed contact fallback
        ch = row.get("contact_hash")
        if ch:
            key = ("contact_hash", str(ch))
            clusters.setdefault(
                key,
                {
                    "contact_type": "contact_hash",
                    "value": str(ch),
                    "students": set(),
                    "institutions": set(),
                },
            )
            clusters[key]["students"].add(student_id)
            clusters[key]["institutions"].add(inst_id)

    signals: list[Signal] = []

    # Filter clusters meeting suspicious thresholds
    for (_ctype, _val), data in clusters.items():
        students = sorted(list(data["students"]))
        institutions = sorted(list(data["institutions"]))
        cluster_size = len(students)
        inst_count = len(institutions)

        # Flag if shared across multiple institutions or large single-institution cluster
        is_suspicious = (inst_count >= cross_institution_min and cluster_size >= 2) or (
            cluster_size >= min_cluster_size
        )

        if not is_suspicious:
            continue

        base_importance = "critical" if inst_count >= 3 else "high"
        severity = SignalSeverity.calculate(base_importance, affected_count=cluster_size)
        score = min(100.0, 65.0 + inst_count * 10.0 + cluster_size * 2.0)

        # Emit one Signal for each affected institution
        for inst_id in institutions:
            evidence: dict[str, Any] = {
                "student_id": (students[0] if cluster_size == 1 else ", ".join(students[:5])),
                "institution_id": inst_id,
                "reason": (
                    f"Shared {data['contact_type']} '{data['value']}' detected across "
                    f"{inst_count} institution(s) with {cluster_size} student(s)."
                ),
                "cluster_size": cluster_size,
                "affected_institutions": institutions,
                "repeated_values": [data["value"]],
                "contact_type": data["contact_type"],
                "students": students,
                "details": {
                    "cluster_size": cluster_size,
                    "affected_institutions": institutions,
                    "repeated_values": [data["value"]],
                    "contact_type": data["contact_type"],
                    "cross_institution": inst_count > 1,
                    "institution_count": inst_count,
                    "students": students,
                },
            }

            signals.append(
                Signal(
                    signal_id=str(uuid4()),
                    institution_id=inst_id,
                    signal_name="SHARED_CONTACT_CLUSTER",
                    severity=severity,
                    score=round(score, 1),
                    evidence=evidence,
                    description=(
                        f"Suspicious contact cluster: {cluster_size} students across "
                        f"{inst_count} institution(s) share the same {data['contact_type']} "
                        f"'{data['value']}'."
                    ),
                    created_at=datetime.now(UTC),
                )
            )

    return signals
