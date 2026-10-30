# Owner: Dev A
"""Comprehensive tests for Integrity Signals Engine (F15)."""

from __future__ import annotations

from datetime import date
from typing import Any

from engine.signals import (
    SignalRegistry,
    SignalSeverity,
    backdated_signal,
    default_registry,
    eligibility_signal,
    execute_signals,
    shared_contacts_signal,
    zero_attrition_signal,
)
from engine.signals.rules import (
    backdating,
    cap_filling,
    eligibility,
    shared_contact_clusters,
)
from engine.types import Signal

# ==============================================================================
# 1. Eligibility vs APH Rules Tests
# ==============================================================================


def test_eligibility_clean_records() -> None:
    """Clean admissions adhering to APH norms should produce zero signals."""
    clean_records = [
        {
            "student_id": "STU_001",
            "institution_id": "INST_01",
            "programme_code": "BTECH_CSE",
            "category": "general",
            "qualifying_exam_pct": 75.5,
            "seat_pool": "regular",
            "dob": "2005-06-15",
            "admission_date": "2023-08-01",
        },
        {
            "student_id": "STU_002",
            "institution_id": "INST_01",
            "programme_code": "BTECH_CSE",
            "category": "sc",
            "qualifying_exam_pct": 42.0,  # Above reserved threshold of 40%
            "seat_pool": "regular",
            "dob": "2004-10-20",
            "admission_date": "2023-08-01",
        },
    ]
    signals = eligibility_signal(clean_records)
    assert len(signals) == 0


def test_eligibility_qualifying_exam_below_norm() -> None:
    """Detects students admitted below minimum AICTE qualifying marks."""
    records = [
        {
            "student_id": "STU_LOW_GEN",
            "institution_id": "INST_01",
            "programme_code": "BTECH_CSE",
            "category": "general",
            "qualifying_exam_pct": 41.5,  # Below 45% general requirement
            "seat_pool": "regular",
            "dob": "2005-01-01",
            "admission_date": "2023-08-01",
        },
        {
            "student_id": "STU_LOW_RES",
            "institution_id": "INST_01",
            "programme_code": "BTECH_CSE",
            "category": "obc",
            "qualifying_exam_pct": 38.0,  # Below 40% reserved requirement
            "seat_pool": "regular",
            "dob": "2005-01-01",
            "admission_date": "2023-08-01",
        },
    ]
    signals = eligibility_signal(records)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_name == "ELIGIBILITY_VIOLATION"
    assert sig.institution_id == "INST_01"
    assert sig.score >= 70.0
    assert sig.severity in ("review", "error", "warning")

    evidence = sig.evidence
    assert evidence["violations_count"] == 2
    violations = evidence["violations"]
    rules_violated = {v["violated_rule"] for v in violations}
    assert "QUALIFYING_BELOW_NORM" in rules_violated

    # Check evidence structure
    low_gen = next(v for v in violations if v["student_id"] == "STU_LOW_GEN")
    assert low_gen["programme"] == "BTECH_CSE"
    assert ">= 45.0%" in low_gen["expected_value"]
    assert "41.5%" in low_gen["actual_value"]


def test_eligibility_invalid_category_and_quota() -> None:
    """Detects invalid admission categories and unapproved seat pools."""
    records = [
        {
            "student_id": "STU_INV_CAT",
            "institution_id": "INST_02",
            "programme_code": "MBA",
            "category": "vip_quota",  # Unrecognized category
            "qualifying_exam_pct": 60.0,
            "seat_pool": "discretionary_backdoor",  # Unapproved quota
            "dob": "2002-05-10",
            "admission_date": "2023-08-01",
        }
    ]
    signals = eligibility_signal(records)
    assert len(signals) == 1
    evidence = signals[0].evidence
    assert evidence["violations_count"] == 2
    rules = [v["violated_rule"] for v in evidence["violations"]]
    assert "INVALID_CATEGORY" in rules
    assert "INVALID_QUOTA" in rules


def test_eligibility_implausible_age() -> None:
    """Detects students admitted outside plausible age boundaries."""
    records = [
        {
            "student_id": "STU_TOO_YOUNG",
            "institution_id": "INST_03",
            "programme_code": "BTECH_MECH",
            "category": "general",
            "qualifying_exam_pct": 80.0,
            "dob": "2015-01-01",  # 8 years old at admission
            "admission_date": "2023-08-01",
        },
        {
            "student_id": "STU_TOO_OLD",
            "institution_id": "INST_03",
            "programme_code": "BTECH_MECH",
            "category": "general",
            "qualifying_exam_pct": 75.0,
            "dob": "1960-01-01",  # 63 years old
            "admission_date": "2023-08-01",
        },
    ]
    signals = eligibility_signal(records)
    assert len(signals) == 1
    evidence = signals[0].evidence
    assert evidence["violations_count"] == 2
    assert all(v["violated_rule"] == "AGE_IMPLAUSIBLE" for v in evidence["violations"])


def test_eligibility_exceeded_intake() -> None:
    """Detects when an institution exceeds approved intake capacity."""
    seat_pools = [
        {
            "institution_id": "INST_OVERRUN",
            "programme_code": "MCA",
            "approved_seats": 2,
        }
    ]
    records = [
        {
            "student_id": f"STU_MCA_{i}",
            "institution_id": "INST_OVERRUN",
            "programme_code": "MCA",
            "category": "general",
            "qualifying_exam_pct": 65.0,
            "dob": "2002-01-01",
            "admission_date": "2023-08-01",
        }
        for i in range(3)
    ]
    signals = eligibility_signal(records, seat_pools=seat_pools)
    assert len(signals) == 1
    evidence = signals[0].evidence
    violations = evidence["violations"]
    overrun = next(v for v in violations if v["violated_rule"] == "EXCEEDED_INTAKE")
    assert overrun["programme"] == "MCA"
    assert "<= 2 seats" in overrun["expected_value"]
    assert "3 admitted" in overrun["actual_value"]


def test_eligibility_programme_eligibility_configurable() -> None:
    """Configurable rules can enforce allowed programmes."""
    records = [
        {
            "student_id": "STU_UNAPPROVED_PROG",
            "institution_id": "INST_PROG",
            "programme_code": "UNAPPROVED_DIPLOMA",
            "category": "general",
            "qualifying_exam_pct": 70.0,
            "dob": "2003-01-01",
        }
    ]
    rules_cfg = {
        "valid_programmes": {"BTECH_CSE", "BTECH_ECE", "MBA"},
    }
    signals = eligibility_signal(records, rules_config=rules_cfg)
    assert len(signals) == 1
    evidence = signals[0].evidence
    assert evidence["violated_rule"] == "INVALID_PROGRAMME_ELIGIBILITY"
    assert evidence["programme"] == "UNAPPROVED_DIPLOMA"


# ==============================================================================
# 2. Shared Contact Clusters Tests
# ==============================================================================


def test_shared_contacts_across_institutions() -> None:
    """Detects phone numbers and emails shared across distinct institutions."""
    records = [
        {
            "student_id": "STU_A1",
            "institution_id": "INST_A",
            "contact_phone": "+91 98765 43210",
            "contact_email": "agent@suspicious-consultancy.com",
        },
        {
            "student_id": "STU_B1",
            "institution_id": "INST_B",
            "contact_phone": "9876543210",
            "contact_email": "student_b@example.com",
        },
        {
            "student_id": "STU_C1",
            "institution_id": "INST_C",
            "guardian_phone": "9876543210",
            "contact_email": "agent@suspicious-consultancy.com",
        },
    ]
    signals = shared_contacts_signal(records, min_cluster_size=2, cross_institution_min=2)
    assert len(signals) > 0

    # Ensure signals are emitted for affected institutions
    flagged_institutions = {s.institution_id for s in signals}
    assert "INST_A" in flagged_institutions
    assert "INST_B" in flagged_institutions
    assert "INST_C" in flagged_institutions

    # Check evidence structure
    sample_signal = signals[0]
    assert sample_signal.signal_name == "SHARED_CONTACT_CLUSTER"
    ev = sample_signal.evidence
    assert ev["cluster_size"] >= 2
    assert len(ev["affected_institutions"]) >= 2
    assert len(ev["repeated_values"]) > 0
    assert "students" in ev


def test_shared_contacts_clean_singletons() -> None:
    """Unique phone numbers and emails should raise zero signals."""
    records = [
        {
            "student_id": f"STU_CLEAN_{i}",
            "institution_id": f"INST_{i}",
            "contact_phone": f"987654320{i}",
            "contact_email": f"student{i}@university.ac.in",
        }
        for i in range(5)
    ]
    signals = shared_contacts_signal(records)
    assert len(signals) == 0


def test_shared_contacts_single_institution_large_cluster() -> None:
    """A large cluster within a single institution triggers threshold alerts."""
    records = [
        {
            "student_id": f"STU_CLUSTER_{i}",
            "institution_id": "INST_MONO",
            "contact_phone": "9998887770",
        }
        for i in range(4)
    ]
    signals = shared_contacts_signal(records, min_cluster_size=3)
    assert len(signals) == 1
    assert signals[0].institution_id == "INST_MONO"
    assert signals[0].evidence["cluster_size"] == 4


# ==============================================================================
# 3. Backdated Admissions Tests
# ==============================================================================


def test_backdated_admissions_detected() -> None:
    """Flag admissions uploaded significantly later than stated admission date."""
    records = [
        {
            "student_id": "STU_BACKDATED_1",
            "institution_id": "INST_DELAY",
            "admission_date": "2023-01-15",
            "upload_date": "2023-04-15",  # 90 days delay
        },
        {
            "student_id": "STU_BACKDATED_2",
            "institution_id": "INST_DELAY",
            "admission_date": "2023-01-20",
            "upload_date": "2023-03-25",  # 64 days delay
        },
        {
            "student_id": "STU_ON_TIME",
            "institution_id": "INST_DELAY",
            "admission_date": "2023-03-01",
            "upload_date": "2023-03-10",  # 9 days delay (within 30d limit)
        },
    ]
    signals = backdated_signal(records, max_delay_days=30)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_name == "BACKDATED_ADMISSIONS"
    assert sig.institution_id == "INST_DELAY"
    assert sig.score >= 60.0

    ev = sig.evidence
    assert ev["backdated_count"] == 2
    assert ev["threshold_days"] == 30
    assert ev["max_delay_days"] == 90
    assert "admission_date" in ev
    assert "upload_date" in ev
    assert "delay" in ev
    assert "student_id" in ev


def test_backdated_admissions_with_reference_date() -> None:
    """Batch upload reference date applies when individual upload_date is missing."""
    records = [
        {
            "student_id": "STU_REF",
            "institution_id": "INST_REF",
            "admission_date": "2023-01-01",
        }
    ]
    signals = backdated_signal(
        records,
        max_delay_days=30,
        reference_upload_date=date(2023, 3, 1),  # 59 days delay
    )
    assert len(signals) == 1
    assert signals[0].evidence["delay"] == 59


def test_backdated_admissions_clean() -> None:
    """Prompt admissions uploaded within standard window trigger no signals."""
    records = [
        {
            "student_id": "STU_PUNCTUAL",
            "institution_id": "INST_CLEAN",
            "admission_date": "2023-08-01",
            "upload_date": "2023-08-10",
        }
    ]
    signals = backdated_signal(records, max_delay_days=30)
    assert len(signals) == 0


# ==============================================================================
# 4. Zero Attrition Cap Filling Tests
# ==============================================================================


def test_zero_attrition_cap_filling_detected() -> None:
    """Detects institutions with 100% capacity utilization and 0 dropouts over years."""
    history = [
        {
            "institution_id": "INST_SYNTHETIC",
            "academic_year": "2021-22",
            "approved_seats": 120,
            "enrolled_students": 120,
            "attrition_count": 0,
        },
        {
            "institution_id": "INST_SYNTHETIC",
            "academic_year": "2022-23",
            "approved_seats": 120,
            "enrolled_students": 120,
            "attrition_count": 0,
        },
    ]
    signals = zero_attrition_signal(history, min_years=2)
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_name == "ZERO_ATTRITION_CAP_FILLING"
    assert sig.institution_id == "INST_SYNTHETIC"
    assert sig.severity in ("review", "error")

    ev = sig.evidence
    assert ev["utilisation"] == 1.0
    assert ev["attrition"] == 0.0
    assert ev["years_analysed"] == ["2021-22", "2022-23"]
    assert "anomaly_reason" in ev
    assert "synthetic cap-filling" in ev["anomaly_reason"].lower()


def test_zero_attrition_normal_institution_not_flagged() -> None:
    """Normal institution with natural dropout rate should not be flagged."""
    normal_history = [
        {
            "institution_id": "INST_NORMAL",
            "academic_year": "2021-22",
            "approved_seats": 120,
            "enrolled_students": 115,
            "attrition_count": 8,  # Natural attrition ~7%
        },
        {
            "institution_id": "INST_NORMAL",
            "academic_year": "2022-23",
            "approved_seats": 120,
            "enrolled_students": 118,
            "attrition_count": 6,
        },
    ]
    signals = zero_attrition_signal(normal_history, min_years=2)
    assert len(signals) == 0


def test_zero_attrition_insufficient_history() -> None:
    """A single year of 100% utilisation is insufficient to establish a pattern."""
    single_year = [
        {
            "institution_id": "INST_ONE_YEAR",
            "academic_year": "2022-23",
            "approved_seats": 60,
            "enrolled_students": 60,
            "attrition_count": 0,
        }
    ]
    signals = zero_attrition_signal(single_year, min_years=2)
    assert len(signals) == 0


def test_zero_attrition_dict_format() -> None:
    """Accepts nested history dictionary format."""
    data = {
        "institution_id": "INST_DICT_FMT",
        "history": [
            {"academic_year": "2021-22", "utilisation": 1.0, "attrition": 0.0},
            {"academic_year": "2022-23", "utilisation": 1.0, "attrition": 0.0},
        ],
    }
    signals = zero_attrition_signal(data)
    assert len(signals) == 1
    assert signals[0].institution_id == "INST_DICT_FMT"


# ==============================================================================
# 5. SignalRegistry & Execution Tests
# ==============================================================================


def test_registry_registration_and_execution() -> None:
    """Tests custom signal registration, listing, and execution in SignalRegistry."""
    registry = SignalRegistry(register_defaults=False)
    assert len(registry.list_signals()) == 0

    def custom_flag_all(records: list[dict[str, Any]]) -> list[Signal]:
        return [
            Signal(
                institution_id="INST_CUSTOM",
                signal_name="CUSTOM_TEST_SIGNAL",
                severity="info",
                score=50.0,
                evidence={"records_count": len(records)},
                description="Custom test signal executed.",
            )
        ]

    # Register via function
    registry.register(custom_flag_all)
    assert "custom_flag_all" in registry.list_signals()

    # Execute
    records = [{"student_id": "S1"}]
    signals = registry.execute(records)
    assert len(signals) == 1
    assert signals[0].signal_name == "CUSTOM_TEST_SIGNAL"

    # Unregister
    registry.unregister("custom_flag_all")
    assert len(registry.list_signals()) == 0


def test_registry_decorator_registration() -> None:
    """Tests registering signals via decorator syntax."""
    registry = SignalRegistry(register_defaults=False)

    @registry.register("named_signal")
    def my_named_signal(records: list[dict[str, Any]]) -> list[Signal]:
        return []

    assert "named_signal" in registry.list_signals()


def test_default_registry_full_suite() -> None:
    """Verify that default_registry contains all four core signals."""
    signals = default_registry.list_signals()
    assert "eligibility" in signals
    assert "shared_contacts" in signals
    assert "backdated" in signals
    assert "attrition" in signals


def test_execute_signals_composite_payload() -> None:
    """Tests executing signals with composite dictionary containing all data types."""
    composite_data = {
        "admissions": [
            # Ineligible student (low percentage)
            {
                "student_id": "STU_LOW",
                "institution_id": "INST_COMPOSITE",
                "programme_code": "BTECH",
                "category": "general",
                "qualifying_exam_pct": 30.0,
                "admission_date": "2023-01-01",
                "upload_date": "2023-04-01",  # 90d delay -> backdated
                "contact_phone": "9991112223",
            },
            {
                "student_id": "STU_SHARED",
                "institution_id": "INST_OTHER",
                "contact_phone": "9991112223",  # Shared phone across institutions
            },
        ],
        "historical_stats": [
            {
                "institution_id": "INST_COMPOSITE",
                "academic_year": "2021-22",
                "approved_seats": 100,
                "enrolled_students": 100,
                "attrition_count": 0,
            },
            {
                "institution_id": "INST_COMPOSITE",
                "academic_year": "2022-23",
                "approved_seats": 100,
                "enrolled_students": 100,
                "attrition_count": 0,
            },
        ],
    }

    results = execute_signals(composite_data)
    signal_names = {s.signal_name for s in results}
    assert "ELIGIBILITY_VIOLATION" in signal_names
    assert "SHARED_CONTACT_CLUSTER" in signal_names
    assert "BACKDATED_ADMISSIONS" in signal_names
    assert "ZERO_ATTRITION_CAP_FILLING" in signal_names


# ==============================================================================
# 6. Backward Compatibility (rules.py)
# ==============================================================================


def test_rules_py_compatibility() -> None:
    """Ensure existing engine.signals.rules functions run without NotImplementedError."""
    admissions = [
        {
            "student_id": "STU_R1",
            "institution_id": "INST_R",
            "programme_code": "BTECH",
            "category": "general",
            "qualifying_exam_pct": 25.0,
            "admission_date": "2023-01-01",
            "upload_date": "2023-05-01",
            "contact_phone": "9876500001",
        },
        {
            "student_id": "STU_R2",
            "institution_id": "INST_R2",
            "contact_phone": "9876500001",
        },
    ]

    elig_signals = eligibility(admissions)
    assert len(elig_signals) >= 1

    contact_signals = shared_contact_clusters(admissions, min_size=2)
    assert len(contact_signals) >= 1

    backdate_signals = backdating(admissions)
    assert len(backdate_signals) >= 1

    seat_pools = [{"institution_id": "INST_R", "programme_code": "BTECH", "approved_seats": 0}]
    cap_signals = cap_filling(admissions, seat_pools)
    assert len(cap_signals) >= 1


# ==============================================================================
# 7. Edge Cases & Malformed Data
# ==============================================================================


def test_malformed_and_empty_inputs() -> None:
    """Signals should never raise exceptions on malformed or empty data."""
    # Empty inputs
    assert eligibility_signal([]) == []
    assert shared_contacts_signal([]) == []
    assert backdated_signal([]) == []
    assert zero_attrition_signal([]) == []
    assert execute_signals([]) == []
    assert execute_signals({}) == []

    # Corrupted / non-dict records
    corrupted_records = [
        None,
        "not a dict",
        {},
        {"invalid_key": 123},
        {"student_id": None, "institution_id": None},
        {"qualifying_exam_pct": "not_a_float", "dob": "bad_date"},
        {"admission_date": "invalid", "upload_date": 99999},
    ]  # type: ignore[list-item]

    assert isinstance(eligibility_signal(corrupted_records), list)
    assert isinstance(shared_contacts_signal(corrupted_records), list)
    assert isinstance(backdated_signal(corrupted_records), list)
    assert isinstance(zero_attrition_signal(corrupted_records), list)
    assert isinstance(execute_signals(corrupted_records), list)


def test_signal_severity_scaling() -> None:
    """Verify SignalSeverity calculations scale with importance and are capped at review."""
    assert SignalSeverity.calculate("low", affected_count=1) == "info"
    assert SignalSeverity.calculate("medium", affected_count=2) == "warning"
    assert SignalSeverity.calculate("medium", affected_count=15) == "review"
    assert SignalSeverity.calculate("high", affected_count=1) == "review"
    # Capped at review (never error; error rows get excluded from commit)
    assert SignalSeverity.calculate("high", affected_count=6) == "review"
    assert SignalSeverity.calculate("critical", affected_count=1) == "review"
    assert SignalSeverity.calculate("critical", affected_count=5) == "review"
    assert SignalSeverity.calculate("high", institution_wide=True) == "review"


# ==============================================================================
# 8. Upload Hook Contract (shared/engine-hooks.md)
# ==============================================================================


def test_engine_hooks_contract_eligibility() -> None:
    """Verify eligibility hook matches shared/engine-hooks.md contract specifications."""
    # Row dicts as specified in Section 2
    rows = [
        {
            "row_number": 1,
            "upload_date": "2026-10-23",
            "institution_aicte_code": "1-9999003",
            "programme_code": "UG-CSE",
            "academic_year": "2026-27",
            "student_name": "Aarav Sharma",
            "dob": "2008-03-14",
            "gender": "male",
            "category": "general",
            "pwd": False,
            "apaar_id": None,
            "apaar_opt_out": False,
            "provisional_id": "PROV001",
            "nationality": "INDIAN",
            "oci_status": False,
            "fn_status": False,
            "nri_category": False,
            "seat_pool": "regular",
            "admission_mode": "cap",
            "admission_date": "2026-08-15",
            "qualifying_exam": "HSC",
            "qualifying_exam_pct": 42.0,  # Below general norm (45.0)
            "domicile_state": "Maharashtra",
            "contact_phone": "hmac:abc123phone",
            "contact_email": "hmac:abc123email",
            "guardian_name": "Rakesh Sharma",
        },
        {
            "row_number": 2,
            "upload_date": "2026-10-23",
            "institution_aicte_code": "1-9999003",
            "programme_code": "UG-CSE",
            "academic_year": "2026-27",
            "student_name": "Priya Patel",
            "dob": "2007-11-20",
            "gender": "female",
            "category": "sc",
            "pwd": None,
            "apaar_id": "123456789012",
            "apaar_opt_out": False,
            "provisional_id": None,
            "nationality": "INDIAN",
            "oci_status": None,
            "fn_status": None,
            "nri_category": None,
            "seat_pool": "regular",
            "admission_mode": "cap",
            "admission_date": "2026-08-20",
            "qualifying_exam": "HSC",
            "qualifying_exam_pct": 38.5,  # Below SC/reserved norm (40.0)
            "domicile_state": "Gujarat",
            "contact_phone": None,
            "contact_email": None,
            "guardian_name": None,
        },
        {
            "row_number": 3,
            "upload_date": "2026-10-23",
            "institution_aicte_code": "1-9999003",
            "programme_code": "UG-CSE",
            "academic_year": "2026-27",
            "student_name": "Rahul Verma",
            "dob": "2008-01-10",
            "gender": "male",
            "category": "general",
            "pwd": False,
            "apaar_id": None,
            "apaar_opt_out": False,
            "provisional_id": "PROV003",
            "nationality": "INDIAN",
            "oci_status": False,
            "fn_status": False,
            "nri_category": False,
            "seat_pool": "regular",
            "admission_mode": "cap",
            "admission_date": "2026-08-25",
            "qualifying_exam": "HSC",
            "qualifying_exam_pct": 72.0,  # Eligible
            "domicile_state": "Delhi",
            "contact_phone": "hmac:xyzphone",
            "contact_email": "hmac:xyzemail",
            "guardian_name": "Suresh Verma",
        },
        {
            "row_number": 4,
            "upload_date": "2026-10-23",
            "institution_aicte_code": "1-9999003",
            "programme_code": "UG-CSE",
            "academic_year": "2026-27",
            "student_name": "Sneha Roy",
            "dob": "2008-05-05",
            "gender": "female",
            "category": None,  # None category must never become "none"
            "pwd": None,
            "apaar_id": None,
            "apaar_opt_out": False,
            "provisional_id": None,
            "nationality": "INDIAN",
            "oci_status": None,
            "fn_status": None,
            "nri_category": None,
            "seat_pool": None,
            "admission_mode": None,
            "admission_date": None,
            "qualifying_exam": None,
            "qualifying_exam_pct": None,  # None percentage tolerated
            "domicile_state": None,
            "contact_phone": None,
            "contact_email": None,
            "guardian_name": None,
        },
    ]

    signals = eligibility(rows)
    assert len(signals) == 2

    # Section 3: Check code, severity, and evidence shape
    for s in signals:
        assert s.code == "QUALIFYING_BELOW_NORM"
        assert s.severity in ("warning", "review")  # Never error
        assert "row_numbers" in s.evidence
        assert isinstance(s.evidence["row_numbers"], list)
        assert len(s.evidence["row_numbers"]) > 0
        assert all(isinstance(rn, int) for rn in s.evidence["row_numbers"])
        assert "reason" in s.evidence
        assert isinstance(s.evidence["reason"], str)
        # Ensure no PII in reason
        for pii in ["Aarav", "Sharma", "Priya", "Patel"]:
            assert pii not in s.evidence["reason"]

    flagged_rows = {rn for s in signals for rn in s.evidence["row_numbers"]}
    assert flagged_rows == {1, 2}


def test_engine_hooks_contract_backdating() -> None:
    """Verify backdating hook matches shared/engine-hooks.md contract specifications."""
    rows = [
        {
            "row_number": 10,
            "upload_date": "2026-10-23",
            "academic_year": "2026-27",
            "admission_date": "2026-04-15",  # March-May (before July-September window)
            "institution_aicte_code": "1-1234567",
        },
        {
            "row_number": 11,
            "upload_date": "2026-10-23",
            "academic_year": "2026-27",
            "admission_date": "2026-08-10",  # Normal July-September admission
            "institution_aicte_code": "1-1234567",
        },
        {
            "row_number": 12,
            "upload_date": "2026-10-23",
            "academic_year": "2026-27",
            "admission_date": None,  # Missing date tolerated
            "institution_aicte_code": "1-1234567",
        },
    ]

    signals = backdating(rows)
    assert len(signals) == 1

    s = signals[0]
    assert s.code == "BACKDATED_ENTRY"
    assert s.severity in ("warning", "review")  # Never error
    assert s.evidence["row_numbers"] == [10]
    assert "reason" in s.evidence
    assert "before the July" in s.evidence["reason"]


def test_engine_hooks_contract_blind_match_encoder() -> None:
    """Verify Blind Match encode_identity and dice match shared/engine-hooks.md."""
    import pytest

    from engine.blind_match.encoder import dice, encode_identity

    fields_a = {
        "student_name": "Aarav Sharma",
        "dob": "2008-03-14",
        "guardian_name": "Rakesh Sharma",
    }
    secret = b"my-super-secret-key-for-test-32b"

    enc_a = encode_identity(fields_a, secret, bits=1024, k=20)
    assert isinstance(enc_a, bytes)
    assert len(enc_a) == 1024 // 8  # Exactly 128 bytes

    # Determinism
    enc_a_repeat = encode_identity(fields_a, secret, bits=1024, k=20)
    assert enc_a == enc_a_repeat
    assert dice(enc_a, enc_a_repeat) == 1.0

    # Changes when secret changes
    enc_different_secret = encode_identity(
        fields_a, b"different-secret-key-32b-length", bits=1024, k=20
    )
    assert enc_a != enc_different_secret

    # Raises ValueError when secret is empty or missing
    with pytest.raises(ValueError, match="secret"):
        encode_identity(fields_a, b"", bits=1024, k=20)
