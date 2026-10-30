# Owner: Dev A
"""Unit and integration tests for Feature F24 Evaluation Pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.evaluation.pipeline import run_evaluation_pipeline


def test_f24_pipeline_execution_on_synthetic_dataset(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dataset_dir = repo_root / "datagen" / "out"

    if not dataset_dir.is_dir() or not (dataset_dir / "ground_truth.csv").is_file():
        pytest.skip("datagen/out not generated; run datagen first")

    out_file = tmp_path / "test_results.json"
    results = run_evaluation_pipeline(dataset_dir=dataset_dir, output_json=out_file)

    assert out_file.is_file()
    assert "blind_match" in results
    assert "plaintext_fuzzy" in results
    assert "overall" in results

    bm = results["blind_match"]
    assert "shared_contact_cluster" in bm
    assert "backdated_entry" in bm
    assert "typo_duplicate" in bm
    assert "dup_cross_institution" in bm
    assert "intake_overrun" in bm
    assert "opted_out" not in bm  # Must be ignored

    # Check that intake_overrun passed on pool level
    assert bm["intake_overrun"]["tp"] == 3
    assert bm["intake_overrun"]["fp"] == 0
    assert bm["intake_overrun"]["fn"] == 0
    assert bm["intake_overrun"]["f1"] == 1.0

    # Check backdated entry
    assert bm["backdated_entry"]["tp"] == 16
    assert bm["backdated_entry"]["f1"] == 1.0

    # Check shared contact cluster
    assert bm["shared_contact_cluster"]["tp"] == 16
    assert bm["shared_contact_cluster"]["f1"] == 1.0

    # Check dup cross institution
    assert bm["dup_cross_institution"]["tp"] == 10
    assert bm["dup_cross_institution"]["f1"] == 1.0

    # Headline Live Backend Blind Match: 0 false positives (tp=12, fp=0, f1=1.0)
    # using keyed HMAC of full normalized DOB blocking
    assert bm["typo_duplicate"]["tp"] == 12
    assert bm["typo_duplicate"]["fp"] == 0
    assert bm["typo_duplicate"]["recall"] == 1.0
    assert bm["typo_duplicate"]["precision"] == 1.0
    assert bm["typo_duplicate"]["f1"] == 1.0

    # Comparative Birth-Year Blocking run: 1 false positive on two Ijaya Aggarwals in 2007
    assert "birth_year_blind_match" in results
    by_bm = results["birth_year_blind_match"]
    assert by_bm["typo_duplicate"]["tp"] == 12
    assert by_bm["typo_duplicate"]["fp"] == 1
    assert by_bm["typo_duplicate"]["recall"] == 1.0
    assert by_bm["typo_duplicate"]["precision"] == 0.9231
    assert by_bm["typo_duplicate"]["f1"] == 0.96
    assert "two Ijaya Aggarwals" in by_bm["typo_duplicate"]["note"]

    # Plaintext fuzzy matcher has 1 false positive due to unencrypted name collisions
    plain = results["plaintext_fuzzy"]
    assert plain["typo_duplicate"]["tp"] == 12
    assert plain["typo_duplicate"]["fp"] == 1
    assert plain["typo_duplicate"]["precision"] == 0.9231
    assert plain["typo_duplicate"]["recall"] == 1.0
    assert plain["typo_duplicate"]["f1"] == 0.96

    # Overall metrics
    overall_bm = results["overall"]["blind_match"]
    assert overall_bm["micro_precision"] == 1.0
    assert overall_bm["micro_recall"] == 1.0
    assert overall_bm["micro_f1"] == 1.0
    assert overall_bm["macro_f1"] == 1.0

    overall_by = results["overall"]["birth_year_blind_match"]
    assert overall_by["micro_precision"] == 0.9828
    assert overall_by["micro_recall"] == 1.0
    assert overall_by["micro_f1"] == 0.9913
    assert overall_by["macro_f1"] == 0.992

    overall_plain = results["overall"]["plaintext_fuzzy"]
    assert overall_plain["micro_precision"] == 0.9828
    assert overall_plain["micro_recall"] == 1.0
    assert overall_plain["micro_f1"] == 0.9913
    assert overall_plain["macro_f1"] == 0.992
