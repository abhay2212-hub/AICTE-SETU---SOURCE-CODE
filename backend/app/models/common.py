# Owner: Dev B
"""Value sets shared across domains. Keep in sync with the enums in supabase/migrations."""

from __future__ import annotations

from typing import Literal

SeatPool = Literal["regular", "tfw", "fn_oci_pio", "nri"]
AdmissionMode = Literal["cap", "management", "lateral", "spot"]
AdmissionStatus = Literal[
    "submitted", "student_confirmed", "student_disputed", "no_response", "withdrawn"
]
BatchStatus = Literal["uploaded", "mapped", "validated", "committed", "failed"]
IssueSeverity = Literal["error", "warning", "review", "info"]
CaseStatus = Literal["open", "confirmed", "dismissed", "correction_requested"]
CaseKind = Literal["intake_overrun", "blind_match", "dispute", "signal"]
Gender = Literal["male", "female", "transgender"]
Category = Literal["general", "ews", "obc", "sc", "st"]
ReportFormat = Literal["json", "pdf", "xlsx"]
