# Feature F24 Evaluation Report: Black-Box Production Benchmark

## 1. Executive Summary

This report documents the end-to-end evaluation of the actual **live production paths** and **engine reference implementations** for the APAAR Integrity Platform (Feature F24).

The evaluation pipeline is architected as a strict **black-box evaluator**:
```
Synthetic Dataset (admissions.csv, intake.csv)
       ↓
Production Components (Live Backend Paths & Engine Reference Rules)
       ↓
Production Signals & Review Cases (predictions sealed in memory)
       ↓
Ground Truth (ground_truth.csv loaded ONLY after predictions are sealed)
       ↓
Precision / Recall / F1 & Micro/Macro Aggregates
```

The evaluator contains **zero duplicate detection logic**, **zero hardcoded benchmark parameters**, and maintains **absolute ground-truth isolation** (predictions are finalized and sealed before `ground_truth.csv` is accessed).

> [!IMPORTANT]
> **Deterministic Benchmark Scope:** This benchmark measures the algorithmic performance of the live production system and engine reference implementations against a deterministic synthetic dataset (`seed=42`, 25 institutions, 5,063 student admissions, 396 seat pools). It does **NOT** claim real-world operational accuracy. In real-world national deployments, unmodeled data drift, varying institutional naming standards, OCR artifacts, and missing guardian data will naturally affect precision and recall.

---

## 2. Dataset & Scope

- **Dataset Directory:** `datagen/out/` (gitignored; generated locally)
- **Exact Generation Command:**
  ```bash
  cd datagen && uv run python generate.py --seed 42 --institutions 25 --students 5000 --out out
  ```
- **Admissions Dataset:** 5,063 records (`admissions.csv`) across 25 institutions and 396 seat pools (`intake.csv`).
- **Ground Truth File:** `datagen/out/ground_truth.csv` (128 total labelled entries).
- **Target Anomalies Evaluated (57 planted cases):**
  - `shared_contact_cluster`: 16 student records (2 distinct institutional clusters sharing phone and email)
  - `backdated_entry`: 16 student records (management admissions backdated to March–May 2026, months prior to the July 1 window)
  - `typo_duplicate`: 12 student duplicate pairs (cross-institution single-letter typographical copies with missing or alternate APAAR)
  - `dup_cross_institution`: 10 student duplicate pairs (exact duplicate APAAR enrollments across distinct institutions)
  - `intake_overrun`: 3 approved seat pools (pools exceeding approved capacity by 10–25%)
- **Excluded Anomaly:**
  - `opted_out` (71 records): Excluded from anomaly evaluation because opting out of APAAR with an institutional provisional ID is a valid statutory workflow under AICTE guidelines, not an integrity anomaly.

---

## 3. Production Component Mapping: Live Backend vs. Engine Reference

To ensure scientific precision, this benchmark distinguishes between what runs in the live backend service and the engine reference implementations:

| Anomaly / Signal Type | Live Production Backend Path | Engine Reference Implementation | Evaluated Granularity |
| :--- | :--- | :--- | :--- |
| `intake_overrun` | **Seat Ledger** (`backend/app/services/batches.py`): tracks committed pool seats vs approved intake | `cap_filling(admissions, seat_pools)` (`engine.signals.rules`) | Pool-level (`inst\|prog\|year\|pool`) |
| `shared_contact_cluster` | **Validation Rule** (`backend/app/services/validation.py`): clusters on contact hashes with `threshold = 5` | `shared_contact_clusters(admissions, min_size=5)` (`engine.signals.rules`) | Record-level (`record_id`) |
| `backdated_entry` | **Upload Hook** (`backend/app/services/validation.py`): directly calls `rules.backdating(rows)` | `backdating(admissions)` (`engine.signals.rules`) | Record-level (`record_id`) |
| `dup_cross_institution` | **Validation Rule** (`backend/app/services/validation.py`): checks active cross-institution enrollments | `find_exact_apaar_duplicates(students)` (`engine.blind_match.service`) | Pair-level $(u, v)$ |
| `typo_duplicate` | **Live Blind Match** (`backend/app/services/blind_match.py`): HMAC full DOB blocking, `bits=1024`, `dice` $\ge 0.85$ | `BlindMatchService` (`engine.blind_match.service`) with `BirthYearBlocking` (`YYYY`) | Pair-level $(u, v)$ |

---

## 4. Benchmark Performance Metrics Breakdown

### Pipeline A: Headline Live Backend Production Path (Full DOB HMAC Blocking)

The headline live production system blocks on a keyed HMAC of the full normalized date of birth (`dob_block_key`), compares only across different institutions, skips pairs with matching APAAR/provisional IDs, and scores via `encode_identity(bits=1024)` + `dice` with `MATCH_THRESHOLD = 0.85`.

| Signal / Anomaly Type | Component Path | Support | TP | FP | FN | Precision | Recall | F1-Score |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `shared_contact_cluster` | Live Backend Validation Rule | 16 | 16 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** |
| `backdated_entry` | Live Backend Hook (`rules.backdating`) | 16 | 16 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** |
| `typo_duplicate` | **Live Backend Blind Match (Full DOB)** | 12 | 12 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** |
| `dup_cross_institution` | Live Backend Validation Rule | 10 | 10 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** |
| `intake_overrun` | Live Backend Seat Ledger | 3 | 3 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** |
| **Headline Micro Summary** | — | **57** | **57** | **0** | **0** | **1.0000** | **1.0000** | **1.0000** |
| **Headline Macro Summary** | — | **57** | — | — | — | **1.0000** | **1.0000** | **1.0000** |

---

### Pipeline B: Comparative Engine Reference Run (Birth-Year Blocking)

This comparative run evaluates the engine reference implementation using `BirthYearBlocking` (`YYYY`) from `engine/src/engine/blind_match/linkage.py`.

| Signal / Anomaly Type | Component Path | Support | TP | FP | FN | Precision | Recall | F1-Score | Note |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `shared_contact_cluster` | Engine Reference | 16 | 16 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** | Cluster size $\ge 5$ |
| `backdated_entry` | Engine Reference | 16 | 16 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** | AICTE window rules |
| `typo_duplicate` | **Engine Blind Match (`BirthYearBlocking`)** | 12 | 12 | 1 | 0 | **0.9231** | **1.0000** | **0.9600** | **1 FP (two Ijaya Aggarwals, different DOB)** |
| `dup_cross_institution` | Engine Reference | 10 | 10 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** | Exact APAAR detector |
| `intake_overrun` | Engine Reference (`cap_filling`) | 3 | 3 | 0 | 0 | **1.0000** | **1.0000** | **1.0000** | Pool capacity rules |
| **Engine Micro Summary** | — | **57** | **57** | **1** | **0** | **0.9828** | **1.0000** | **0.9913** | |
| **Engine Macro Summary** | — | **57** | — | — | — | **0.9846** | **1.0000** | **0.9920** | |

---

### Pipeline C: Plain-Text Fuzzy Matching Baseline (Exact DOB Blocking)

Evaluates unencrypted pairwise RapidFuzz string ratio on normalized student names within identical birth date blocks.

| Signal / Anomaly Type | Component Path | Support | TP | FP | FN | Precision | Recall | F1-Score | Note |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `typo_duplicate` | Plain-Text RapidFuzz | 12 | 12 | 1 | 0 | **0.9231** | **1.0000** | **0.9600** | 1 FP: `Eta Banerjee` vs `Neha Banerjee` |

---

## 5. Architectural Slide Point: Why Live Production Blocks on Full DOB

Comparing Pipeline A (Live Backend Full DOB) against Pipeline B (Engine Birth-Year Blocking) provides a crucial engineering insight for SIH judging:

1. **Why Full DOB Blocking in Live Production?**
   - In birth-year blocking (`YYYY`), every student born in a given year is compared against every other student born that year across all institutions.
   - In the benchmark dataset, records `R0002917` ("Ijaya Aggarwal", born `2007-11-22` at `1-9900015`) and `R0004971` ("Ijaya Aggarwal", born `2007-12-23` at `1-9900025`) share the 2007 birth year block. With identical student names and guardian tokens, their Bloom filter Dice score is **0.8531** ($\ge 0.85$), triggering **1 False Positive** and lowering precision to **92.31%**.
   - By blocking on the **keyed HMAC of the full normalized date of birth** (`dob_block_key`), the live backend ensures students born in different months are never co-blocked. This eliminates coincidental name collisions across birth cohorts, achieving **100% precision (0 FP)** in the live system.

2. **Architectural Trade-Off & Limitation:**
   - **DOB Typo Vulnerability:** Because the live backend blocks strictly on the full normalized DOB, any typographical error planted in the date of birth itself (e.g. `2004-05-12` vs `2004-05-13`) places the two records into distinct HMAC blocks. Such pairs escape Blind Match detection unless supplementary blocking keys (e.g., soundex of name + birth year) are deployed.

---

## 6. Verification of Live Behaviors

### 1. `rules.eligibility` Hook Form
The engine hook contract (`shared/engine-hooks.md`) specifies that when `rules.eligibility` is invoked during batch upload validation, it receives row dicts containing `row_number`.
- Verification confirms that [`engine/src/engine/signals/rules.py`](file:///c:/Users/Chinmay/Desktop/Vs%20Code/apaar-integrity-platform/engine/src/engine/signals/rules.py#L30) executes the per-row validation hook path and **only emits `Signal(code="QUALIFYING_BELOW_NORM", severity="warning")`**.
- It does **not** emit pool capacity violations or unexpected codes in hook mode.

### 2. `SHARED_CONTACT_THRESHOLD`
- The live backend uses `shared_contact_threshold = 5` (`.env.example` and `backend/app/core/config.py`).
- In the synthetic dataset, both planted clusters contain $\ge 6$ students (one cluster of 6, one cluster of 10). Both threshold 5 and threshold 6 correctly flag all 16 planted records with 0 false positives.
- `engine.config` aligns with the live backend default of `SHARED_CONTACT_THRESHOLD = 5`.

---

## 7. Reproducibility

To reproduce all metrics from a clean repository checkout:

1. Generate the deterministic synthetic dataset:
   ```bash
   cd datagen
   uv run python generate.py --seed 42 --institutions 25 --students 5000 --out out
   cd ..
   ```

2. Run the evaluation pipeline:
   ```bash
   uv run python -m engine.evaluation.pipeline datagen/out evaluation/results.json
   ```

3. Run the automated test suites:
   ```bash
   uv run pytest engine/tests
   uv run pytest backend/tests/test_validation_rules.py
   ```

All results serialize directly to [`evaluation/results.json`](file:///c:/Users/Chinmay/Desktop/Vs%20Code/apaar-integrity-platform/evaluation/results.json).
