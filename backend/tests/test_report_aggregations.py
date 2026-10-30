# Owner: Dev C
from __future__ import annotations

import unittest

import pandas as pd

from app.services.report_aggregations import (
    accreditation_programmes,
    accreditation_report,
    category_admission_rows,
    enrolment_rows,
    latest_intake,
    programme_utilisation_rows,
)

ADMISSIONS = pd.DataFrame(
    [
        {
            "programme_id": "p1",
            "programme_code": "UG-CSE",
            "state": "Maharashtra",
            "category": "general",
            "gender": "female",
            "opted_out": False,
            "active": True,
        },
        {
            "programme_id": "p1",
            "programme_code": "UG-CSE",
            "state": "Maharashtra",
            "category": "obc",
            "gender": "male",
            "opted_out": True,
            "active": True,
        },
        {
            "programme_id": "p2",
            "programme_code": "UG-ME",
            "state": None,
            "category": None,
            "gender": "male",
            "opted_out": None,
            "active": True,
        },
        {
            "programme_id": "p2",
            "programme_code": "UG-ME",
            "state": "Delhi",
            "category": "general",
            "gender": "female",
            "opted_out": False,
            "active": False,
        },
    ]
)
INTAKE = pd.DataFrame(
    [
        {
            "programme_id": "p1",
            "programme_code": "UG-CSE",
            "pool": "regular",
            "approved_seats": 50,
            "rule_version": "APH-v1",
        },
        {
            "programme_id": "p1",
            "programme_code": "UG-CSE",
            "pool": "regular",
            "approved_seats": 60,
            "rule_version": "APH-v2",
        },
        {
            "programme_id": "p1",
            "programme_code": "UG-CSE",
            "pool": "tfw",
            "approved_seats": 5,
            "rule_version": "APH-v2",
        },
        {
            "programme_id": "p2",
            "programme_code": "UG-ME",
            "pool": "regular",
            "approved_seats": 0,
            "rule_version": "APH-v2",
        },
        {
            "programme_id": "p3",
            "programme_code": "UG-CE",
            "pool": "regular",
            "approved_seats": 10,
            "rule_version": "APH-v2",
        },
    ]
)


class AggregationTests(unittest.TestCase):
    def test_enrolment_groups_and_missing_values(self) -> None:
        self.assertEqual(
            enrolment_rows(ADMISSIONS, "state").to_dict("records"),
            [
                {"group": "<unknown>", "admissions": 1, "opted_out": 0},
                {"group": "Maharashtra", "admissions": 2, "opted_out": 1},
            ],
        )
        self.assertEqual(enrolment_rows(ADMISSIONS, "programme")["admissions"].sum(), 3)
        self.assertEqual(enrolment_rows(ADMISSIONS, "category").iloc[0]["group"], "<unknown>")
        self.assertEqual(enrolment_rows(ADMISSIONS, "gender")["admissions"].sum(), 3)

    def test_empty_enrolment(self) -> None:
        empty = ADMISSIONS.iloc[0:0]
        self.assertEqual(enrolment_rows(empty, "state").to_dict("records"), [])
        self.assertEqual(category_admission_rows(empty).to_dict("records"), [])

    def test_latest_intake_and_zero_safe_programme_utilisation(self) -> None:
        latest = latest_intake(INTAKE)
        self.assertEqual(len(latest), 4)
        cse_regular = latest[(latest["programme_id"] == "p1") & (latest["pool"] == "regular")]
        self.assertEqual(cse_regular.iloc[0]["approved_seats"], 60)

        rows = programme_utilisation_rows(ADMISSIONS, INTAKE).set_index("programme_code")
        self.assertEqual(rows.loc["UG-CSE", "approved_seats"], 65)
        self.assertEqual(rows.loc["UG-CSE", "admitted"], 2)
        self.assertAlmostEqual(rows.loc["UG-CSE", "utilisation"], 2 / 65)
        self.assertIsNone(rows.loc["UG-ME", "utilisation"])
        self.assertEqual(rows.loc["UG-CE", "admitted"], 0)
        self.assertEqual(rows.loc["UG-CE", "approved_seats"], 10)
        self.assertEqual(rows.loc["UG-CE", "utilisation"], 0.0)

    def test_category_counts_do_not_invent_utilisation(self) -> None:
        rows = category_admission_rows(ADMISSIONS).to_dict("records")
        self.assertEqual(
            rows,
            [
                {"category": "<unknown>", "admitted": 1},
                {"category": "general", "admitted": 1},
                {"category": "obc", "admitted": 1},
            ],
        )
        self.assertNotIn("utilisation", rows[0])

    def test_accreditation_contract_data(self) -> None:
        programmes = accreditation_programmes(ADMISSIONS, INTAKE).set_index("programme_code")
        self.assertEqual(programmes.loc["UG-CSE", "overrun"], 0)
        self.assertEqual(programmes.loc["UG-ME", "overrun"], 1)
        self.assertEqual(programmes.loc["UG-CE", "admitted_total"], 0)
        report = accreditation_report(
            {"institution_id": "i1", "institution_name": "Synthetic Institute"},
            ADMISSIONS,
            INTAKE,
            academic_year="2026-27",
            integrity_score=88.5,
            apaar_coverage_pct=97.0,
            open_review_cases=2,
        )
        self.assertEqual(report["institution_id"], "i1")
        self.assertEqual(
            report["programmes"], accreditation_programmes(ADMISSIONS, INTAKE).to_dict("records")
        )

    def test_accreditation_without_integrity_score(self) -> None:
        report = accreditation_report(
            {"institution_id": "i1", "institution_name": "Synthetic Institute"},
            ADMISSIONS,
            INTAKE,
            academic_year="2026-27",
            integrity_score=None,
            apaar_coverage_pct=0.0,
            open_review_cases=0,
            integrity_note="not yet computed",
        )
        self.assertIsNone(report["integrity_score"])
        self.assertEqual(report["integrity_note"], "not yet computed")

    def test_programmes_with_seats_and_no_admissions(self) -> None:
        programmes = accreditation_programmes(ADMISSIONS.iloc[0:0], INTAKE)
        self.assertEqual(
            programmes.set_index("programme_code")["admitted_total"].to_dict(),
            {"UG-CE": 0, "UG-CSE": 0, "UG-ME": 0},
        )
        self.assertEqual(int(programmes["overrun"].sum()), 0)

    def test_missing_required_column_is_reported(self) -> None:
        with self.assertRaisesRegex(ValueError, "state"):
            enrolment_rows(ADMISSIONS.drop(columns="state"), "state")


if __name__ == "__main__":
    unittest.main()
