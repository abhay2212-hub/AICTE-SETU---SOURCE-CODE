<!-- Owner: Dev A -->
# engine

Integrity engine for the APAAR Integrity Platform. The backend imports it as `engine` (editable dependency).

| Module | Purpose | Status |
| --- | --- | --- |
| `engine.types` | Shared dataclasses (`MatchCase`, `Signal`, `IntegrityScore`, `AnomalyResult`, etc.) | done |
| `engine.config` | Engine configuration defaults | done |
| `engine.routers` | FastAPI router endpoints (`/engine`, `/engine/health`, `/engine/blind-match`, `/engine/signals`, `/engine/anomaly`, `/engine/integrity-score`, `/engine/evaluate`) | done |
| `engine.blind_match.encoder` | Text normalization, character bigrams, birth year salting, HMAC Bloom-filter encoding | done |
| `engine.blind_match.similarity` | Dice and Jaccard similarity metrics over bit arrays | done |
| `engine.blind_match.models` | `BloomFilter`, `StudentRecord`, `LinkageMatch`, and `ReviewCaseRepository` interfaces | done |
| `engine.blind_match.linkage` | Candidate pairs blocked on hashed birth year with Dice threshold filtering | done |
| `engine.blind_match.service` | `BlindMatchService` and exact APAAR cross-institution duplicate detection | done |
| `engine.signals.base` | Signal severity mapping and evidence builders | done |
| `engine.signals.eligibility` | Eligibility vs AICTE APH rules violation detection | done |
| `engine.signals.shared_contacts` | Suspicious shared contact clusters across institutions | done |
| `engine.signals.backdated` | Backdated admissions detection with delay thresholds | done |
| `engine.signals.attrition` | Zero attrition repeated cap filling analysis | done |
| `engine.signals.registry` | Extensible `SignalRegistry` and execution engine | done |
| `engine.signals.rules` | Backward-compatible wrappers for rule signals | done |
| `engine.anomaly.features` | Institution feature extraction and typed vector generation | done |
| `engine.anomaly.model` | Modular anomaly detection models (`BaseAnomalyModel`, `IsolationForestModel`) | done |
| `engine.anomaly.service` | `AnomalyDetectionService` with explainability and model substitution | done |
| `engine.anomaly.isolation` | Isolation Forest ranking of institutions | done |
| `engine.scoring.weights` | Configurable scoring weights and classification thresholds | done |
| `engine.scoring.calculator` | Deterministic `IntegrityScoreCalculator` combining signals, anomaly, and matches | done |
| `engine.scoring.service` | `IntegrityScoringService` for single institution and batch evaluations | done |
| `engine.scoring.integrity` | Backward-compatible `integrity_score` function | done |
| `engine.evaluation.metrics` | Classification rates (Precision, Recall, F1, Accuracy, FPR, FNR) & ROC AUC | done |
| `engine.evaluation.datasets` | Ground truth evaluation dataset format and synthetic benchmark generator | done |
| `engine.evaluation.benchmark` | Benchmarking runner measuring component latency and throughput | done |
| `engine.evaluation.report` | Structured, deterministic `EvaluationReport` format | done |
| `engine.evaluation.service` | `EvaluationService` multi-domain verification framework | done |
| `engine.eval.harness` / `engine.evaluation.harness` | Signal precision, recall and F1 against datagen ground truth | done |

---

## Integrity Signals Engine Architecture (Feature F15)

The Integrity Signals Engine provides rule-based intelligence detecting suspicious admission patterns at both the student and institution level.

```
Admission Records / Institution History
                     ↓
             [Signal Registry]
                     ↓
  ┌──────────────────┼──────────────────┬──────────────────┐
  ↓                  ↓                  ↓                  ↓
[Signal 1:         [Signal 2:         [Signal 3:         [Signal 4:
 Eligibility vs     Shared Contact     Backdated          Zero Attrition
 APH Rules]         Clusters]          Admissions]        Cap Filling]
  │                  │                  │                  │
  └──────────────────┴──────────────────┴──────────────────┘
                     ↓
        Configurable Severity & Confidence Scoring
                     ↓
          Structured Evidence Generation
                     ↓
             List of `Signal` Outputs
```

### Core Design Principles

1. **Pure Functions**: Every signal is implemented as a deterministic, stateless pure function with no database queries or HTTP dependencies.
2. **Standard Signal Contract**: Every signal outputs the existing `Signal` model (`signal_id`, `institution_id`, `signal_name`, `severity`, `score`, `evidence`, `description`, `created_at`).
3. **Structured Evidence**: All outputs provide strictly typed, structured evidence dictionaries rather than free-form text.
4. **Independent Extensibility**: New signals are added and registered dynamically via `SignalRegistry` without altering existing signals.

---

### Core Signals

#### 1. Eligibility vs APH Rules (`eligibility.py`)
Flags student admissions violating AICTE Approval Process Handbook (APH) norms:
- **Qualifying Exam %**: Compares student marks against minimum thresholds (45% for general, 40% for reserved categories).
- **Category Validation**: Enforces approved admission categories (`general`, `ews`, `obc`, `sc`, `st`).
- **Quota Validation**: Enforces recognized seat pools (`regular`, `tfw`, `fn_oci_pio`, `nri`).
- **Plausible Age**: Validates student age at admission (default: 16–35 years).
- **Approved Intake Overrun**: Flags programmes where total admissions exceed approved capacity.
- **Programme Eligibility**: Validates programme codes against configured eligible offerings.

#### 2. Shared Contact Clusters (`shared_contacts.py`)
Identifies suspicious sharing of phone numbers, guardian phone numbers, and emails across institutions:
- Groups students sharing identical normalized contact credentials.
- Flags clusters spanning multiple institutions or exceeding cluster size thresholds within single institutions (indicative of unregulated admission brokers).

#### 3. Backdated Admissions (`backdated.py`)
Detects admissions uploaded significantly later than their declared admission date:
- Calculates elapsed days between declared `admission_date` and upload timestamp.
- Flags delays exceeding configurable thresholds (default: 30 days).

#### 4. Zero Attrition Cap Filling (`attrition.py`)
Analyzes multi-year institution statistics to detect synthetic cap filling:
- Evaluates seat utilisation and student dropout/attrition rates over consecutive academic years.
- Flags institutions exhibiting consistently 100% capacity utilization with 0% attrition across 2+ years.

---

### Signal Severity & Scoring

- **Severity Levels**: Mapped to platform standards (`"info"`, `"warning"`, `"review"`, `"error"`).
- **Dynamic Calculation**: `SignalSeverity.calculate(base_importance, affected_count, institution_wide)` scales severity according to rule criticality, number of affected students, and institution impact.
- **Confidence Scoring**: Each signal includes a confidence score between 0.0 and 100.0 based on sample size and deviation magnitude.

---

### Evidence Format

All signals produce structured evidence compliant with the platform contract:

```json
{
  "student_id": "STU_001",
  "institution_id": "INST_01",
  "reason": "1 admission eligibility violation(s) detected under AICTE APH norms.",
  "violated_rule": "QUALIFYING_BELOW_NORM",
  "programme": "BTECH_CSE",
  "expected_value": ">= 45.0%",
  "actual_value": "41.5%",
  "violations_count": 1,
  "violations": [
    {
      "violated_rule": "QUALIFYING_BELOW_NORM",
      "student_id": "STU_001",
      "programme": "BTECH_CSE",
      "expected_value": ">= 45.0%",
      "actual_value": "41.5%",
      "reason": "Qualifying percentage 41.5% is below AICTE minimum 45.0% for category 'general'"
    }
  ],
  "details": {
    "violations_count": 1,
    "violations": [...]
  }
}
```

---

### Signal Registry Design & Adding New Signals

`SignalRegistry` manages signal registration, discovery, and execution:

```python
from engine.signals import SignalRegistry, Signal
from engine.types import Signal

registry = SignalRegistry()

# 1. Register via decorator
@registry.register("my_custom_rule")
def my_custom_rule(admissions: list[dict]) -> list[Signal]:
    signals = []
    # Pure rule logic...
    return signals

# 2. Register via direct call
registry.register("another_rule", another_rule_fn)

# 3. Execute all registered signals against records
signals = registry.execute(records)
```

The global default registry provides pre-registered core signals:
```python
from engine.signals import execute_signals

# Executes all default core signals
signals = execute_signals(institution_data)
```

---

### API Usage

#### POST `/engine/signals`

Executes in-memory integrity signals against institution admissions, seat pools, or historical statistics.

**Request:**

```json
{
  "admissions": [
    {
      "student_id": "stud-1",
      "institution_id": "inst-1",
      "programme_code": "BTECH_CSE",
      "category": "general",
      "qualifying_exam_pct": 38.0,
      "dob": "2005-05-15",
      "admission_date": "2023-01-10",
      "upload_date": "2023-04-15",
      "contact_phone": "9876543210"
    },
    {
      "student_id": "stud-2",
      "institution_id": "inst-2",
      "contact_phone": "9876543210"
    }
  ],
  "historical_stats": [
    {
      "institution_id": "inst-1",
      "academic_year": "2021-22",
      "approved_seats": 100,
      "enrolled_students": 100,
      "attrition_count": 0
    },
    {
      "institution_id": "inst-1",
      "academic_year": "2022-23",
      "approved_seats": 100,
      "enrolled_students": 100,
      "attrition_count": 0
    }
  ]
}
```

**Response (`200 OK`):**

```json
[
  {
    "signal_id": "19bfa6a1-0e11-4f11-9252-875883d659ad",
    "institution_id": "inst-1",
    "signal_name": "ELIGIBILITY_VIOLATION",
    "severity": "review",
    "score": 75.0,
    "evidence": {
      "institution_id": "inst-1",
      "student_id": "stud-1",
      "violated_rule": "QUALIFYING_BELOW_NORM",
      "programme": "BTECH_CSE",
      "expected_value": ">= 45.0%",
      "actual_value": "38.0%",
      "reason": "1 admission eligibility violation(s) detected under AICTE APH norms.",
      "violations_count": 1,
      "violations": [...]
    },
    "description": "Institution has 1 student admission(s) violating AICTE APH eligibility rules.",
    "created_at": "2026-10-23T12:00:00Z"
  },
  {
    "signal_id": "76e31cba-274c-4375-a8ea-c4309307779d",
    "institution_id": "inst-1",
    "signal_name": "SHARED_CONTACT_CLUSTER",
    "severity": "review",
    "score": 89.0,
    "evidence": {
      "cluster_size": 2,
      "affected_institutions": ["inst-1", "inst-2"],
      "repeated_values": ["9876543210"],
      "contact_type": "phone",
      "students": ["stud-1", "stud-2"]
    },
    "description": "Suspicious contact cluster: 2 students across 2 institution(s) share the same phone '9876543210'.",
    "created_at": "2026-10-23T12:00:00Z"
  },
  {
    "signal_id": "9a01e234-884c-4235-802e-503417a80b01",
    "institution_id": "inst-1",
    "signal_name": "BACKDATED_ADMISSIONS",
    "severity": "error",
    "score": 77.5,
    "evidence": {
      "institution_id": "inst-1",
      "student_id": "stud-1",
      "admission_date": "2023-01-10",
      "upload_date": "2023-04-15",
      "delay": 95,
      "backdated_count": 1,
      "threshold_days": 30
    },
    "description": "Institution entered 1 admission(s) with excessive delay (up to 95 days) beyond the 30-day threshold.",
    "created_at": "2026-10-23T12:00:00Z"
  },
  {
    "signal_id": "0133ac24-110f-488b-b152-32a2ef39c8f2",
    "institution_id": "inst-1",
    "signal_name": "ZERO_ATTRITION_CAP_FILLING",
    "severity": "review",
    "score": 85.0,
    "evidence": {
      "institution_id": "inst-1",
      "utilisation": 1.0,
      "attrition": 0.0,
      "years_analysed": ["2021-22", "2022-23"],
      "anomaly_reason": "Institution exhibits 100.0% seat utilisation with 0.0% student attrition across 2 consecutive academic years (2021-22, 2022-23), indicating synthetic cap-filling."
    },
    "description": "Repeated cap filling with zero attrition: 100% utilization across 2 academic years.",
    "created_at": "2026-10-23T12:00:00Z"
  }
]
```

---

## Blind Match Architecture

The Blind Match engine enables privacy-preserving duplicate student detection across AICTE-approved institutions without exposing raw Personally Identifiable Information (PII) to central storage or untrusted third parties.

```
Student PII (Name, DOB, Parents' Names)
                ↓
    [1. Normalization] (NFKD, lowercase, strip punctuation/spaces)
                ↓
    [2. Bigram Generation] ("RAHUL" → "ra", "ah", "hu", "ul")
                ↓
    [3. Birth Year Salting & Scoping] (e.g. "2004:student_name:ra")
                ↓
    [4. HMAC-SHA256 Double Hashing] (k=20 bit positions via h1 + i*h2 mod 1024)
                ↓
    [5. Bloom Filter Encoding] (1024-bit immutable bit array)
                ↓
    [6. Hashed Birth Year Blocking] (HMAC-SHA256 block key)
                ↓
    [7. Pairwise Dice Similarity Linkage] (Dice >= MATCH_THRESHOLD)
                ↓
    [8. Cross-Institution Review Cases] (MatchCase outputs)
```

### Bloom Filter Explanation

1. **Text Normalization**: Unicode text is decomposed into ASCII base forms via NFKD, converted to lowercase, stripped of non-alphanumeric punctuation, and trimmed of excess whitespace.
2. **Bigram Extraction**: Field values are converted into 2-character sliding shingles (e.g., `"RAHUL"` produces `["ra", "ah", "hu", "ul"]`).
3. **Birth Year Salting**: Bigram tokens are prefixed with the student's birth year and field name (`{birth_year}:{field_name}:{bigram}`). This ensures cross-field separation and defends against frequency analysis across birth cohorts.
4. **HMAC-SHA256 Double Hashing**: Each token is hashed using HMAC-SHA256 keyed with `BLIND_MATCH_SECRET`. The 32-byte digest is split into `h1` and `h2`, generating $k=20$ unique bit positions inside a 1024-bit vector:
   $$\text{position}_i = (h1 + i \times h2) \pmod{1024}$$
5. **Configurable Field Weights**: Weights per field determine the proportion of bit positions allocated.

### Dice Similarity

The Dice similarity coefficient quantifies the bitwise overlap between two 1024-bit Bloom filters $A$ and $B$:

$$\text{Dice}(A, B) = \frac{2 \times |A \cap B|}{|A| + |B|}$$

- $\text{Dice} = 1.0$ for identical student profiles.
- $\text{Dice} \approx 0.85\text{--}0.95$ for profiles with minor typos or transliteration discrepancies.
- $\text{Dice} < 0.70$ for distinct individuals.

### Privacy Guarantees

- **One-Way Transformation**: Cryptographic HMAC-SHA256 prevents inversion of Bloom filters back into raw student names.
- **Cohort Salting**: Using hashed birth year salting thwarts dictionary and frequency attacks across the national student dataset.
- **Non-PII Linkage**: Only Bloom filter encodings and hashed block keys are shared for pairwise linkage. Raw names and Aadhaar/APAAR identities remain protected.

### Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `MATCH_THRESHOLD` | `0.85` | Minimum Dice similarity required to flag a potential cross-institution duplicate. |
| `MODEL_VERSION` | `0.1.0` | Active model / pipeline version. |
| `BLIND_MATCH_SECRET` | `default-insecure-blind-match-key-32b` | Secret HMAC key used to derive Bloom filter bit positions and block hashes. |

### API Usage

#### POST `/engine/blind-match`

Submits student records to execute in-memory privacy-preserving fuzzy matching and exact APAAR duplicate detection across institutions.

**Request:**

```json
{
  "records": [
    {
      "student_id": "stud-1",
      "institution_id": "inst-1",
      "student_name": "Aarav Sharma",
      "dob": "2004-05-15",
      "father_name": "Vijay Sharma",
      "mother_name": "Sunita Sharma",
      "apaar_id": "999900001111"
    },
    {
      "student_id": "stud-2",
      "institution_id": "inst-2",
      "student_name": "Aarav Sharma",
      "dob": "2004-05-15",
      "father_name": "Vijay Sharma",
      "mother_name": "Sunita Sharma",
      "apaar_id": "999900001111"
    }
  ],
  "threshold": 0.85
}
```

**Response (`200 OK`):**

```json
[
  {
    "case_id": "8488e0f6-...",
    "institution_a": "inst-1",
    "institution_b": "inst-2",
    "student_a_id": "stud-1",
    "student_b_id": "stud-2",
    "similarity_score": 1.0,
    "confidence": 1.0,
    "matched_fields": ["apaar_id"],
    "status": "open",
    "created_at": "2026-10-23T11:45:00Z"
  }
]
```

---

## Institution Intelligence Layer

The Institution Intelligence Layer aggregates signals and duplicate linkages into institution-level risk intelligence through machine learning and deterministic scoring.

```
+------------------------------------+    +------------------------------------+
|       Blind Match Candidates       |    |       Rule-Based Signals           |
| (Cross-Institution Duplicate Cases)|    | (Eligibility, Contact Clusters...) |
+------------------+-----------------+    +------------------+-----------------+
                   |                                         |
                   +--------------------+--------------------+
                                        |
                                        v
                    +---------------------------------------+
                    | Feature Engineering (features.py)     |
                    | Extract 10-dimensional feature vector |
                    +-------------------+-------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
  +------------------------------+             +-------------------------------+
  | ML Anomaly Detection (F16)   |             | Integrity Score (F17)         |
  | Isolation Forest Model       |             | Deterministic Deductions      |
  | Anomaly Score & Heuristic    |             | Risk Level Mapping            |
  | Feature Importance           |             | Configurable Weights          |
  +--------------+---------------+             +---------------+---------------+
                 |                                             |
                 +----------------------+----------------------+
                                        |
                                        v
                         +-----------------------------+
                         | Comprehensive Assessment    |
                         | IntegrityScore & Risk Level |
                         +-----------------------------+
```

---

## Feature Engineering (`engine.anomaly.features`)

The feature extractor converts raw multi-domain institution records (admissions, historical statistics, signals, match cases) into a strongly-typed, normalized 10-dimensional feature vector:

| Feature Name | Description | Source |
| --- | --- | --- |
| `seat_utilisation` | Latest enrolled students / approved intake capacity | `historical_stats` or `seat_pools` |
| `intake_growth` | Year-over-year percentage change in student enrollment | Consecutive `historical_stats` years |
| `duplicate_rate` | Exact duplicate APAAR/student IDs / total admissions | Admission records |
| `blind_match_rate` | Cross-institution fuzzy duplicate cases / total admissions | Blind Match candidate cases |
| `shared_contact_rate` | Proportion of students sharing phone/guardian contacts | Admission records |
| `backdated_admission_rate` | Admissions with upload delay > threshold / total admissions | `admission_date` vs `upload_date` |
| `eligibility_violation_count` | Count of student admissions violating AICTE APH minimum criteria | `qualifying_exam_pct` < 45.0% |
| `zero_attrition_frequency` | Proportion of years with 100% utilisation and 0% attrition | Multi-year `historical_stats` |
| `average_signal_severity` | Mean numeric severity across all generated signals | `error`: 4.0, `review`: 3.0, `warning`: 2.0, `info`: 1.0 |
| `total_signals_generated` | Total volume of rule signals raised against the institution | Aggregated `Signal` records |

The extractor handles missing values gracefully, guards against division by zero, and accepts both raw records and pre-calculated feature dictionaries.

```python
from engine.anomaly import extract_institution_features

# Pure functional feature extraction
vector = extract_institution_features("inst-001", institution_data)
feature_dict = vector.to_dict()
feature_array = vector.to_array()
```

---

## ML Anomaly Detection (Feature F16)

### Modular ML Architecture

The anomaly detection engine decouples model training from scoring and explainability:
- **`BaseAnomalyModel`**: Abstract base class defining `fit(X)`, `predict(X)`, and `score_samples(X)`. Allows future drop-in replacement with alternate models (e.g., Local Outlier Factor, One-Class SVM, or Autoencoders).
- **`IsolationForestModel`**: Scikit-learn `IsolationForest` implementation using deterministic random state (`MODEL_RANDOM_SEED`), configurable contamination (`ANOMALY_CONTAMINATION`), and normalized anomaly scoring in `[0.0, 1.0]`.
- **`AnomalyDetectionService`**: Orchestrates feature transformation, training, prediction, and feature importance explanations.

### Isolation Forest Usage & Anomaly Scoring

Isolation Forest builds an ensemble of isolation trees. Inliers require many random partitioning splits, whereas anomalies are isolated near the root of the trees.
- In scikit-learn, `score_samples(X)` returns negative anomaly scores $-s(x) \in (-1, 0)$.
- The engine maps this directly to normalized anomaly score: $\text{score} = - \text{score\_samples}(X)$, clamped to $[0.0, 1.0]$.
- Scores close to $0.0$ indicate clean/typical institutions; scores exceeding $0.5$ indicate anomalous admission patterns.

### Feature Importance & Explainability

Without external explainability dependencies, the engine provides lightweight, fast feature attribution based on standard z-score deviation from the dataset mean:

$$z_j = \frac{x_j - \mu_j}{\max(\sigma_j, 10^{-4})}$$

For flagged institutions, features exhibiting the highest positive deviations above the cohort mean are returned as `top_features`, clearly detailing why an institution was flagged.

---

## Institution Integrity Score (Feature F17)

### Scoring Algorithm

The Integrity Score is a deterministic, unified metric from **0 (worst)** to **100 (clean)**.

$$\text{Score} = \text{clamp}\Big(100.0 - \big(\text{Signal Deduction} + \text{Anomaly Deduction} + \text{Blind Match Deduction}\big), 0.0, 100.0\Big)$$

1. **Signal Deduction**:
   $$\text{Penalty}_{\text{signals}} = \min\left(\text{max\_signal\_penalty}, \sum \text{severity\_weight}(s)\right) \times \text{signal\_weight}$$
2. **Anomaly Deduction**:
   $$\text{Penalty}_{\text{anomaly}} = \min\left(\text{max\_anomaly\_penalty}, \text{anomaly\_score} \times \text{max\_anomaly\_penalty}\right) \times \text{anomaly\_weight}$$
3. **Blind Match Deduction**:
   $$\text{Penalty}_{\text{bm}} = \min\left(\text{max\_bm\_penalty}, \sum \text{base\_penalty} \times \text{confidence}\right) \times \text{blind\_match\_weight}$$

All deductions are recorded under `components` for auditability.

### Risk Level Classification

Institutions are classified into four risk tiers based on configurable thresholds:
- **Low Risk**: $\text{Score} \ge \text{threshold\_low}$ (Default: $\ge 80.0$)
- **Medium Risk**: $\text{threshold\_medium} \le \text{Score} < \text{threshold\_low}$ (Default: $60.0 \le \text{Score} < 80.0$)
- **High Risk**: $\text{threshold\_high} \le \text{Score} < \text{threshold\_medium}$ (Default: $40.0 \le \text{Score} < 60.0$)
- **Critical Risk**: $\text{Score} < \text{threshold\_high}$ (Default: $< 40.0$)

---

## Configuration Reference

| Variable | Default | Description |
| --- | --- | --- |
| `MATCH_THRESHOLD` | `0.85` | Minimum Dice similarity required for blind match linkage. |
| `MODEL_VERSION` | `0.1.0` | Engine pipeline version. |
| `ANOMALY_CONTAMINATION` | `0.1` | Expected proportion of outliers in the training population. |
| `MODEL_RANDOM_SEED` | `42` | Random seed ensuring deterministic Isolation Forest training. |
| `SIGNAL_WEIGHT` | `0.40` | Weight applied to rule-based signal deductions. |
| `ANOMALY_WEIGHT` | `0.35` | Weight applied to ML anomaly deductions. |
| `BLIND_MATCH_WEIGHT` | `0.25` | Weight applied to cross-institution duplicate deductions. |
| `SEVERITY_WEIGHT_ERROR` | `25.0` | Base penalty points for error-level signals. |
| `SEVERITY_WEIGHT_REVIEW` | `15.0` | Base penalty points for review-level signals. |
| `SEVERITY_WEIGHT_WARNING` | `8.0` | Base penalty points for warning-level signals. |
| `SEVERITY_WEIGHT_INFO` | `2.0` | Base penalty points for info-level signals. |
| `SCORE_THRESHOLD_LOW` | `80.0` | Score threshold for Low risk classification. |
| `SCORE_THRESHOLD_MEDIUM` | `60.0` | Score threshold for Medium risk classification. |
| `SCORE_THRESHOLD_HIGH` | `40.0` | Score threshold for High risk classification. |

---

## API Usage

### 1. POST `/engine/anomaly`

Executes in-memory ML anomaly detection over institution feature vectors.

**Request:**

```json
{
  "institutions": [
    {
      "institution_id": "inst-1",
      "features": {
        "seat_utilisation": 0.85,
        "duplicate_rate": 0.01
      }
    },
    {
      "institution_id": "inst-2",
      "features": {
        "seat_utilisation": 2.40,
        "duplicate_rate": 0.55,
        "backdated_admission_rate": 0.80,
        "eligibility_violation_count": 35.0
      }
    }
  ]
}
```

**Response (`200 OK`):**

```json
[
  {
    "institution_id": "inst-1",
    "score": 0.385,
    "prediction": "normal",
    "top_features": [],
    "feature_vector": {
      "seat_utilisation": 0.85,
      "duplicate_rate": 0.01, ...
    }
  },
  {
    "institution_id": "inst-2",
    "score": 0.692,
    "prediction": "anomalous",
    "top_features": [
      "seat_utilisation",
      "backdated_admission_rate",
      "eligibility_violation_count"
    ],
    "feature_vector": {
      "seat_utilisation": 2.40,
      "duplicate_rate": 0.55, ...
    }
  }
]
```

### 2. POST `/engine/integrity-score`

Computes the unified 0–100 Integrity Score and risk assessment for an institution.

**Request:**

```json
{
  "institution_id": "inst-apex",
  "anomaly_score": 0.45,
  "signals": [
    {
      "signal_name": "ELIGIBILITY_VIOLATION",
      "severity": "review",
      "score": 75.0,
      "evidence": {
        "violated_rule": "QUALIFYING_BELOW_NORM"
      }
    }
  ],
  "blind_matches": [
    {
      "institution_a": "inst-apex",
      "institution_b": "inst-other",
      "similarity_score": 0.95,
      "confidence": 0.90
    }
  ]
}
```

**Response (`200 OK`):**

```json
{
  "institution_id": "inst-apex",
  "score": 83.72,
  "risk_level": "low",
  "generated_at": "2026-10-23T12:00:00Z",
  "signals": [
    {
      "signal_id": "...",
      "institution_id": "inst-apex",
      "signal_name": "ELIGIBILITY_VIOLATION",
      "severity": "review",
      "score": 75.0,
      "evidence": { "violated_rule": "QUALIFYING_BELOW_NORM" },
      "description": "",
      "created_at": "..."
    }
  ],
  "components": {
    "signals_deduction": 6.0,
    "anomaly_deduction": 5.78,
    "blind_match_deduction": 4.5,
    "total_deduction": 16.28
  }
}
```

---

## Evaluation Harness & Benchmarking Framework (Feature F24)

The Evaluation Harness measures the effectiveness and operational performance of all intelligence engine components: Blind Match duplicate detection, rule-based integrity signals, Isolation Forest anomaly detection, and deterministic Integrity Score calculation.

```
+---------------------------------------------------------------------------------+
|                                Evaluation Dataset                               |
| (Labelled Pairs, Planted Signal Records, Ground-Truth Anomalies, Control Insts) |
+---------------------------------------+-----------------------------------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
  +------------------------------+             +-------------------------------+
  | Multi-Domain Verification    |             | Component Benchmarking        |
  | ├── Blind Match Precision/R  |             | ├── Encoding latency & rate   |
  | ├── Signals TP/FP/FN & Rules |             | ├── Linkage comparisons/sec   |
  | ├── Anomaly ROC AUC & Matrix |             | ├── Signals throughput        |
  | └── Scoring Determinism & Map|             | └── Scoring latency           |
  +--------------+---------------+             +---------------+---------------+
                 |                                             |
                 +----------------------+----------------------+
                                        |
                                        v
                         +-----------------------------+
                         | EvaluationReport            |
                         | (evaluation.json Contract)  |
                         +-----------------------------+
```

### Core Design Principles

1. **Zero Database Dependency**: Operates entirely in memory; datasets and reports are fully independent from persistent databases or HTTP services.
2. **Deterministic Reproducibility**: Metrics, confusion matrices, and consistency verifications are strictly reproducible across test executions.
3. **Pluggable Ground Truth**: Standardized dataset format supporting custom JSON files or instant generation via [`create_synthetic_benchmark_dataset()`](file:///c:/Users/Chinmay/Desktop/Vs%20Code/apaar-integrity-platform/engine/src/engine/evaluation/datasets.py).

---

### Evaluation Metrics

The framework evaluates predictions against labelled ground truth using classical statistical metrics:

| Metric | Formula | Description |
| --- | --- | --- |
| **Precision** | $\frac{\text{TP}}{\text{TP} + \text{FP}}$ | Proportion of flagged items that are true violations/duplicates. |
| **Recall (Sensitivity)** | $\frac{\text{TP}}{\text{TP} + \text{FN}}$ | Proportion of actual violations/duplicates successfully detected. |
| **F1 Score** | $2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$ | Harmonic mean balancing precision and recall. |
| **Accuracy** | $\frac{\text{TP} + \text{TN}}{\text{TP} + \text{TN} + \text{FP} + \text{FN}}$ | Overall proportion of correct classifications. |
| **False Positive Rate (FPR)** | $\frac{\text{FP}}{\text{FP} + \text{TN}}$ | Ratio of false alarms among actual negative samples. |
| **False Negative Rate (FNR)** | $\frac{\text{FN}}{\text{TP} + \text{FN}}$ | Ratio of missed violations among actual positive samples. |
| **Specificity** | $\frac{\text{TN}}{\text{TN} + \text{FP}}$ | True negative rate (proportion of clean items confirmed clean). |
| **ROC AUC** | $\int_0^1 \text{TPR}(\text{FPR}) \, d\text{FPR}$ | Area under the Receiver Operating Characteristic curve. |

---

### Component Evaluation Details

#### 1. Blind Match Evaluation
- Compares candidate duplicate pairs flagged by pairwise Dice similarity against ground-truth duplicate and non-duplicate pairs.
- Supports single-threshold evaluation and multi-threshold sweeps (e.g. $[0.70, 0.75, 0.80, 0.85, 0.90, 0.95]$) to evaluate threshold sensitivity.

#### 2. Rule Signals Evaluation
- Measures:
  - `signals_generated`: Total signals raised by the rules engine.
  - `correctly_generated`: True positive signals matching planted violations.
  - `false_signals`: Signals generated on benign admissions.
  - `missed_signals`: Planted violations that went undetected.
- Produces per-rule performance breakdowns for `ELIGIBILITY_VIOLATION`, `SHARED_CONTACT_CLUSTER`, `BACKDATED_ADMISSIONS`, and `ZERO_ATTRITION_CAP_FILLING`.

#### 3. ML Anomaly Detection Evaluation
- Compares Isolation Forest binary predictions against ground-truth anomaly status.
- Evaluates ROC-friendly continuous anomaly score distributions and computes ROC AUC.

#### 4. Integrity Score Evaluation
- Verifies:
  - **Deterministic Outputs**: Re-running the exact same input produces identical scores and component deductions.
  - **Score Stability**: Monotonic score behavior between clean and heavily flagged institutions.
  - **Correct Risk Level Mapping**: Strict validation of thresholds ($\ge 80$ Low, $60\text{--}80$ Medium, $40\text{--}60$ High, $< 40$ Critical).
  - **Configurable Weight Behavior**: Dynamically varying component weights scales deductions predictably.

---

### Benchmarking Utilities

[`BenchmarkRunner`](file:///c:/Users/Chinmay/Desktop/Vs%20Code/apaar-integrity-platform/engine/src/engine/evaluation/benchmark.py) evaluates computational efficiency:
- **Encoding Time**: Measures HMAC-SHA256 Bloom-filter construction throughput in records/sec.
- **Linkage Time**: Measures blocking and pairwise Dice coefficient comparisons.
- **Signal Execution Time**: Measures rule engine throughput in admissions/sec.
- **Anomaly Detection Time**: Measures Isolation Forest fitting, scoring, and explainability latency per institution.
- **Integrity Score Time**: Measures deterministic calculator throughput.

---

### Report Format (`evaluation.json`)

The evaluation framework outputs a deterministic structured JSON report:

```json
{
  "blind_match": {
    "default_threshold": 0.85,
    "metrics": {
      "tp": 2,
      "fp": 0,
      "tn": 1,
      "fn": 0,
      "precision": 1.0,
      "recall": 1.0,
      "f1_score": 1.0,
      "accuracy": 1.0,
      "false_positive_rate": 0.0,
      "false_negative_rate": 0.0
    },
    "threshold_sweep": [
      { "threshold": 0.75, "f1_score": 1.0 },
      { "threshold": 0.85, "f1_score": 1.0 },
      { "threshold": 0.95, "f1_score": 1.0 }
    ]
  },
  "signals": {
    "signals_generated": 4,
    "correctly_generated": 4,
    "false_signals": 0,
    "missed_signals": 0,
    "precision": 1.0,
    "recall": 1.0,
    "f1_score": 1.0,
    "per_signal_statistics": {
      "ELIGIBILITY_VIOLATION": { "precision": 1.0, "recall": 1.0, "f1_score": 1.0 },
      "BACKDATED_ADMISSIONS": { "precision": 1.0, "recall": 1.0, "f1_score": 1.0 }
    }
  },
  "anomaly_detection": {
    "metrics": {
      "precision": 1.0,
      "recall": 1.0,
      "f1_score": 1.0,
      "accuracy": 1.0,
      "roc_auc": 1.0
    }
  },
  "integrity_score": {
    "deterministic_outputs_verified": true,
    "risk_level_mapping_verified": true,
    "configurable_weights_verified": true,
    "score_stability_verified": true,
    "status": "passed"
  },
  "benchmark": {
    "encoding": { "encoding_time_ms": 1.25, "throughput_records_sec": 4800.0 },
    "linkage": { "linkage_time_ms": 0.42 },
    "signals": { "signals_execution_time_ms": 1.15 },
    "anomaly_detection": { "anomaly_detection_time_ms": 12.5 },
    "integrity_score": { "integrity_score_time_ms": 0.35 },
    "total_benchmark_time_ms": 15.67
  },
  "summary": {
    "status": "completed",
    "blind_match_f1": 1.0,
    "signals_f1": 1.0,
    "anomaly_detection_f1": 1.0,
    "mean_accuracy": 1.0,
    "integrity_consistency": "passed"
  },
  "generated_at": "2026-10-23T12:00:00Z"
}
```

---

### API Usage

#### POST `/engine/evaluate`

Executes the in-memory evaluation harness and benchmarks across an uploaded ground truth dataset (or uses the synthetic benchmark suite if an empty object `{}` is supplied).

**Request:**

```json
{
  "dataset_id": "demo-dataset",
  "blind_match": {
    "records": [...],
    "ground_truth": [...]
  },
  "signals": {
    "data": { ... },
    "ground_truth": [...]
  },
  "anomaly_detection": {
    "institutions": [...],
    "ground_truth": { ... }
  }
}
```

**Response (`200 OK`):** Complete `EvaluationReport` structure shown above.

---

## Running Tests

```sh
# Engine test suite
cd engine
uv run pytest

# Lint check
uv run ruff check .
```

Owner: Dev A.
