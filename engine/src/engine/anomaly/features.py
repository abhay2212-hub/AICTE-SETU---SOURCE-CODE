# Owner: Dev A
"""Feature engineering for institution-level anomaly detection."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np

from engine.types import InstitutionFeatures, MatchCase, Signal

FEATURE_NAMES: tuple[str, ...] = (
    "seat_utilisation",
    "intake_growth",
    "duplicate_rate",
    "blind_match_rate",
    "shared_contact_rate",
    "backdated_admission_rate",
    "eligibility_violation_count",
    "zero_attrition_frequency",
    "average_signal_severity",
    "total_signals_generated",
)

SEVERITY_NUMERIC_MAP: dict[str, float] = {
    "error": 4.0,
    "review": 3.0,
    "warning": 2.0,
    "info": 1.0,
}


@dataclass
class InstitutionFeatureVector:
    """Strongly typed feature vector for institution-level anomaly detection."""

    institution_id: str
    seat_utilisation: float = 0.0
    intake_growth: float = 0.0
    duplicate_rate: float = 0.0
    blind_match_rate: float = 0.0
    shared_contact_rate: float = 0.0
    backdated_admission_rate: float = 0.0
    eligibility_violation_count: float = 0.0
    zero_attrition_frequency: float = 0.0
    average_signal_severity: float = 0.0
    total_signals_generated: float = 0.0
    extra_features: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, float]:
        """Convert standard and extra features to a dictionary of floats."""
        d = {
            "seat_utilisation": float(self.seat_utilisation),
            "intake_growth": float(self.intake_growth),
            "duplicate_rate": float(self.duplicate_rate),
            "blind_match_rate": float(self.blind_match_rate),
            "shared_contact_rate": float(self.shared_contact_rate),
            "backdated_admission_rate": float(self.backdated_admission_rate),
            "eligibility_violation_count": float(self.eligibility_violation_count),
            "zero_attrition_frequency": float(self.zero_attrition_frequency),
            "average_signal_severity": float(self.average_signal_severity),
            "total_signals_generated": float(self.total_signals_generated),
        }
        if self.extra_features:
            for k, v in self.extra_features.items():
                d[k] = float(v)
        return d

    def to_array(self, feature_names: Sequence[str] | None = None) -> np.ndarray:
        """Convert features to a 1D numpy array in deterministic feature order."""
        names = feature_names if feature_names is not None else FEATURE_NAMES
        f_dict = self.to_dict()
        return np.array([f_dict.get(name, 0.0) for name in names], dtype=np.float64)

    def to_institution_features(self) -> InstitutionFeatures:
        """Convert to the engine's InstitutionFeatures dataclass."""
        return InstitutionFeatures(
            institution_id=self.institution_id,
            features=self.to_dict(),
        )


class InstitutionFeatureExtractor:
    """Extracts typed feature vectors from raw institution admission records,

    historical statistics, signals, and blind match linkage cases.
    """

    def __init__(
        self,
        backdated_threshold_days: int = 180,
        qualifying_min_pct: float = 45.0,
    ) -> None:
        self.backdated_threshold_days = backdated_threshold_days
        self.qualifying_min_pct = qualifying_min_pct

    def extract(
        self,
        institution_id: str,
        data: dict[str, Any] | InstitutionFeatures | InstitutionFeatureVector,
    ) -> InstitutionFeatureVector:
        """Extract a typed InstitutionFeatureVector from data."""
        if isinstance(data, InstitutionFeatureVector):
            return data

        if isinstance(data, InstitutionFeatures):
            return self._from_feature_dict(data.institution_id or institution_id, data.features)

        if not isinstance(data, dict):
            return InstitutionFeatureVector(institution_id=institution_id)

        # Check if the dictionary already contains pre-calculated features
        if "features" in data and isinstance(data["features"], dict):
            inst_id = str(data.get("institution_id") or institution_id)
            return self._from_feature_dict(inst_id, data["features"])

        # Check if feature keys are directly present at root of dictionary
        direct_matches = [k for k in FEATURE_NAMES if k in data]
        if direct_matches and not any(
            k in data for k in ("admissions", "records", "historical_stats")
        ):
            inst_id = str(data.get("institution_id") or institution_id)
            return self._from_feature_dict(inst_id, data)
        if len(direct_matches) >= 3:
            inst_id = str(data.get("institution_id") or institution_id)
            return self._from_feature_dict(inst_id, data)

        # Otherwise extract from raw multi-domain institution records
        return self._extract_from_raw_records(institution_id, data)

    def _from_feature_dict(
        self, institution_id: str, f_dict: dict[str, Any]
    ) -> InstitutionFeatureVector:
        standard_kwargs: dict[str, float] = {}
        extra: dict[str, float] = {}

        for k, v in f_dict.items():
            try:
                num_v = float(v)
            except (ValueError, TypeError):
                continue

            if k in FEATURE_NAMES:
                standard_kwargs[k] = num_v
            elif k not in ("institution_id",):
                extra[k] = num_v

        return InstitutionFeatureVector(
            institution_id=institution_id,
            seat_utilisation=standard_kwargs.get("seat_utilisation", 0.0),
            intake_growth=standard_kwargs.get("intake_growth", 0.0),
            duplicate_rate=standard_kwargs.get("duplicate_rate", 0.0),
            blind_match_rate=standard_kwargs.get("blind_match_rate", 0.0),
            shared_contact_rate=standard_kwargs.get("shared_contact_rate", 0.0),
            backdated_admission_rate=standard_kwargs.get("backdated_admission_rate", 0.0),
            eligibility_violation_count=standard_kwargs.get("eligibility_violation_count", 0.0),
            zero_attrition_frequency=standard_kwargs.get("zero_attrition_frequency", 0.0),
            average_signal_severity=standard_kwargs.get("average_signal_severity", 0.0),
            total_signals_generated=standard_kwargs.get("total_signals_generated", 0.0),
            extra_features=extra,
        )

    def _extract_from_raw_records(
        self, institution_id: str, data: dict[str, Any]
    ) -> InstitutionFeatureVector:
        admissions: list[dict[str, Any]] = data.get("admissions") or data.get("records") or []
        # Filter for this institution if multi-institution list
        inst_admissions = [
            a
            for a in admissions
            if not a.get("institution_id") or str(a.get("institution_id")) == institution_id
        ]
        total_admissions = len(inst_admissions)

        # 1. Historical stats
        hist_stats: list[dict[str, Any]] = data.get("historical_stats") or []
        inst_stats = [
            h
            for h in hist_stats
            if not h.get("institution_id") or str(h.get("institution_id")) == institution_id
        ]
        # Sort by academic_year if possible
        inst_stats.sort(key=lambda h: str(h.get("academic_year", "")))

        seat_utilisation = 0.0
        intake_growth = 0.0
        zero_attrition_frequency = 0.0

        if inst_stats:
            latest = inst_stats[-1]
            approved = float(latest.get("approved_seats") or 0.0)
            enrolled = float(latest.get("enrolled_students") or 0.0)
            if approved > 0:
                seat_utilisation = enrolled / approved

            if len(inst_stats) >= 2:
                prev = inst_stats[-2]
                prev_enrolled = float(prev.get("enrolled_students") or 0.0)
                if prev_enrolled > 0:
                    intake_growth = (enrolled - prev_enrolled) / prev_enrolled

            # Count zero attrition instances where capacity was full or near full
            zero_attr_years = sum(
                1
                for h in inst_stats
                if float(h.get("attrition_count") or 0.0) == 0.0
                and float(h.get("approved_seats") or 0.0) > 0.0
                and (
                    float(h.get("enrolled_students") or 0.0)
                    >= float(h.get("approved_seats") or 0.0)
                )
            )
            zero_attrition_frequency = zero_attr_years / len(inst_stats)
        elif "seat_pools" in data and total_admissions > 0:
            total_approved = sum(
                float(p.get("approved_seats", 0.0)) for p in data.get("seat_pools", [])
            )
            if total_approved > 0:
                seat_utilisation = total_admissions / total_approved

        # 2. Duplicate rate (exact apaar duplicates or duplicate ids in records)
        duplicate_count = 0
        apaar_seen: set[str] = set()
        for a in inst_admissions:
            apaar = a.get("apaar_id")
            if apaar:
                apaar_str = str(apaar).strip()
                if apaar_str in apaar_seen:
                    duplicate_count += 1
                else:
                    apaar_seen.add(apaar_str)
        duplicate_rate = (duplicate_count / total_admissions) if total_admissions > 0 else 0.0

        # 3. Blind match rate
        matches: list[Any] = data.get("matches") or data.get("blind_matches") or []
        inst_matches = []
        for m in matches:
            if isinstance(m, MatchCase) and (
                m.institution_a == institution_id or m.institution_b == institution_id
            ):
                inst_matches.append(m)
            elif isinstance(m, dict) and (
                m.get("institution_a") == institution_id or m.get("institution_b") == institution_id
            ):
                inst_matches.append(m)
        blind_match_rate = (len(inst_matches) / total_admissions) if total_admissions > 0 else 0.0

        # 4. Shared contact rate
        phones: set[str] = set()
        shared_contact_count = 0
        for a in inst_admissions:
            p = a.get("contact_phone") or a.get("phone") or a.get("guardian_phone")
            if p:
                p_str = str(p).strip()
                if p_str in phones:
                    shared_contact_count += 1
                else:
                    phones.add(p_str)
        shared_contact_rate = (
            (shared_contact_count / total_admissions) if total_admissions > 0 else 0.0
        )

        # 5. Backdated admission rate
        # Matches the per-row BACKDATED_ENTRY rule (engine.signals.rules.backdating):
        # flags admissions dated before July 1 or entered with delay > 180 days.
        backdated_count = 0
        for a in inst_admissions:
            adm_date = a.get("admission_date")
            up_date = a.get("upload_date") or a.get("created_at") or a.get("batch_upload_date")
            if adm_date:
                try:
                    d_adm = self._parse_date(adm_date)
                    d_up = self._parse_date(up_date) if up_date else None
                    if d_adm:
                        academic_year_raw = a.get("academic_year")
                        start_year: int | None = None
                        if academic_year_raw and isinstance(academic_year_raw, str):
                            m = re.match(r"^(\d{4})", academic_year_raw.strip())
                            if m:
                                start_year = int(m.group(1))
                        if start_year is None and d_up:
                            start_year = d_up.year
                        if start_year is None:
                            start_year = d_adm.year

                        window_start = date(start_year, 7, 1)
                        if d_adm < window_start or (
                            d_up and (d_up - d_adm).days > self.backdated_threshold_days
                        ):
                            backdated_count += 1
                except Exception:
                    pass
        backdated_admission_rate = (
            (backdated_count / total_admissions) if total_admissions > 0 else 0.0
        )

        # 6. Eligibility violations
        eligibility_violation_count = 0.0
        for a in inst_admissions:
            pct = a.get("qualifying_exam_pct") or a.get("percentage")
            if pct is not None:
                try:
                    if float(pct) < self.qualifying_min_pct:
                        eligibility_violation_count += 1.0
                except (ValueError, TypeError):
                    pass

        # 7. Signals & severity
        raw_signals: list[Any] = data.get("signals") or []
        inst_signals = []
        for s in raw_signals:
            if isinstance(s, Signal) and (
                not s.institution_id or s.institution_id == institution_id
            ):
                inst_signals.append(s)
            elif isinstance(s, dict) and (
                not s.get("institution_id") or s.get("institution_id") == institution_id
            ):
                inst_signals.append(s)

        total_signals_generated = float(len(inst_signals))
        total_sev = 0.0
        for s in inst_signals:
            sev = s.severity if isinstance(s, Signal) else s.get("severity", "warning")
            total_sev += SEVERITY_NUMERIC_MAP.get(str(sev).lower(), 2.0)
            name = (s.signal_name if isinstance(s, Signal) else s.get("signal_name", "")).upper()
            if "ELIGIBILITY" in name and total_admissions == 0:
                eligibility_violation_count += 1.0

        average_signal_severity = (
            (total_sev / total_signals_generated) if total_signals_generated > 0 else 0.0
        )

        return InstitutionFeatureVector(
            institution_id=institution_id,
            seat_utilisation=round(seat_utilisation, 4),
            intake_growth=round(intake_growth, 4),
            duplicate_rate=round(duplicate_rate, 4),
            blind_match_rate=round(blind_match_rate, 4),
            shared_contact_rate=round(shared_contact_rate, 4),
            backdated_admission_rate=round(backdated_admission_rate, 4),
            eligibility_violation_count=round(eligibility_violation_count, 4),
            zero_attrition_frequency=round(zero_attrition_frequency, 4),
            average_signal_severity=round(average_signal_severity, 4),
            total_signals_generated=round(total_signals_generated, 4),
        )

    @staticmethod
    def _parse_date(d: Any) -> date | None:
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        if isinstance(d, str):
            clean = d.strip()
            # Handle ISO yyyy-mm-dd
            if "T" in clean:
                clean = clean.split("T")[0]
            parts = clean.split("-")
            if len(parts) == 3:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
        return None


def extract_institution_features(
    institution_id: str,
    data: dict[str, Any] | InstitutionFeatures | InstitutionFeatureVector,
) -> InstitutionFeatureVector:
    """Convenience functional interface for extracting institution features."""
    extractor = InstitutionFeatureExtractor()
    return extractor.extract(institution_id, data)
