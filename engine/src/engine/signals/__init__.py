# Owner: Dev A
"""Rule-based integrity signals engine module."""

from __future__ import annotations

from engine.signals.attrition import zero_attrition_signal
from engine.signals.backdated import backdated_signal
from engine.signals.base import SignalSeverity, build_evidence
from engine.signals.eligibility import eligibility_signal
from engine.signals.registry import (
    SignalRegistry,
    default_registry,
    execute_signals,
    get_default_registry,
    register_signal,
)
from engine.signals.shared_contacts import shared_contacts_signal

__all__ = [
    "SignalRegistry",
    "SignalSeverity",
    "backdated_signal",
    "build_evidence",
    "default_registry",
    "eligibility_signal",
    "execute_signals",
    "get_default_registry",
    "register_signal",
    "shared_contacts_signal",
    "zero_attrition_signal",
]
