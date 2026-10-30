# Owner: Dev A
"""Signal detecting suspicious repeated cap filling and zero student attrition."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from engine.signals.base import SignalSeverity
from engine.types import Signal

Row = dict[str, Any]


def zero_attrition_signal(
    historical_stats: list[Row] | dict[str, Any],
    min_years: int = 2,
    min_utilisation: float = 0.99,
    max_attrition: float = 0.01,
) -> list[Signal]:
    """Detect institutions exhibiting consistently 100% utilisation with zero attrition.

    Pure function returning structured evidence with:
    - utilisation
    - attrition
    - years analysed
    - anomaly reason
    """
    if not historical_stats:
        return []

    # Normalize input into a list of row dicts
    if isinstance(historical_stats, dict):
        if "history" in historical_stats:
            inst_id = historical_stats.get("institution_id", "unknown")
            rows = [{"institution_id": inst_id, **item} for item in historical_stats["history"]]
        elif "historical_stats" in historical_stats:
            rows = list(historical_stats["historical_stats"])
        else:
            rows = [historical_stats]
    else:
        rows = list(historical_stats)

    # Group stats by institution
    inst_history: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        inst_id = str(r.get("institution_id") or "unknown")
        inst_history.setdefault(inst_id, []).append(r)

    signals: list[Signal] = []

    for inst_id, records in inst_history.items():
        yearly_analysis: list[dict[str, Any]] = []

        for r in records:
            year = str(r.get("academic_year") or r.get("year") or "UNKNOWN")
            try:
                approved = float(r.get("approved_seats") or r.get("approved_intake") or 0)
            except (ValueError, TypeError):
                approved = 0.0

            try:
                enrolled = float(
                    r.get("enrolled_students") or r.get("admitted_total") or r.get("admitted") or 0
                )
            except (ValueError, TypeError):
                enrolled = 0.0

            # Direct or derived utilisation
            try:
                if "utilisation" in r:
                    util = float(r["utilisation"])
                elif "utilization" in r:
                    util = float(r["utilization"])
                elif approved > 0:
                    util = enrolled / approved
                else:
                    util = 0.0
            except (ValueError, TypeError):
                util = 0.0

            # Direct or derived attrition
            try:
                if "attrition" in r:
                    att = float(r["attrition"])
                elif "attrition_rate" in r:
                    att = float(r["attrition_rate"])
                elif enrolled > 0:
                    dropped = float(r.get("attrition_count") or r.get("dropouts") or 0)
                    att = dropped / enrolled
                else:
                    att = 0.0
            except (ValueError, TypeError):
                att = 0.0

            if approved > 0 or "utilisation" in r or "utilization" in r:
                yearly_analysis.append(
                    {
                        "academic_year": year,
                        "utilisation": util,
                        "attrition": att,
                        "approved_seats": approved,
                        "enrolled": enrolled,
                    }
                )

        if len(yearly_analysis) < min_years:
            continue

        # Check if all analysed years exhibit full utilisation with zero attrition
        all_full_util = all(y["utilisation"] >= min_utilisation for y in yearly_analysis)
        all_zero_attrition = all(y["attrition"] <= max_attrition for y in yearly_analysis)

        if all_full_util and all_zero_attrition:
            years = [y["academic_year"] for y in yearly_analysis]
            avg_util = sum(y["utilisation"] for y in yearly_analysis) / len(yearly_analysis)
            avg_att = sum(y["attrition"] for y in yearly_analysis) / len(yearly_analysis)

            anomaly_reason = (
                f"Institution exhibits {avg_util * 100:.1f}% seat utilisation with "
                f"{avg_att * 100:.1f}% student attrition across {len(years)} consecutive "
                f"academic years ({', '.join(years)}), indicating synthetic cap-filling."
            )

            importance = "critical" if len(years) >= 3 else "high"
            severity = SignalSeverity.calculate(importance, institution_wide=True)
            score = min(100.0, 75.0 + len(years) * 5.0)

            evidence: dict[str, Any] = {
                "institution_id": inst_id,
                "utilisation": round(avg_util, 4),
                "attrition": round(avg_att, 4),
                "years_analysed": years,
                "years_analyzed": years,
                "anomaly_reason": anomaly_reason,
                "reason": anomaly_reason,
                "details": {
                    "utilisation": round(avg_util, 4),
                    "attrition": round(avg_att, 4),
                    "years_analysed": years,
                    "years_analyzed": years,
                    "anomaly_reason": anomaly_reason,
                    "years_count": len(years),
                    "min_years_threshold": min_years,
                    "breakdown": yearly_analysis,
                },
            }

            signals.append(
                Signal(
                    signal_id=str(uuid4()),
                    institution_id=inst_id,
                    signal_name="ZERO_ATTRITION_CAP_FILLING",
                    severity=severity,
                    score=round(score, 1),
                    evidence=evidence,
                    description=(
                        f"Repeated cap filling with zero attrition: "
                        f"{avg_util * 100:.0f}% utilization across {len(years)} academic years."
                    ),
                    created_at=datetime.now(UTC),
                )
            )

    return signals
