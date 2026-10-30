<!-- Owner: Dev C -->
# datagen

Synthetic admissions data for the APAAR Integrity Platform, with planted anomalies and a ground-truth file for evaluating the engine. Everything it produces is synthetic: names come from Faker `en_IN`, APAAR IDs are 12 digits starting with `9999`, and phone numbers and emails are fake (`@example.com`).

## Usage

```sh
uv run python generate.py --small                 # 5 institutions, 300 students
uv run python generate.py                         # 200 institutions, 50000 students (about 10 s)
uv run python generate.py --institutions 50 --students 10000 --seed 7 --out out/run7
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--institutions` | 200 | Number of institutions |
| `--students` | 50000 | Target number of regular admissions (planted rows are added on top) |
| `--seed` | 42 | Seed for Python, NumPy and Faker; same seed gives the same files |
| `--out` | `out/` | Output folder (git-ignored) |
| `--small` | off | Shortcut for 5 institutions and 300 students |

## Output

| File | Format |
| --- | --- |
| `institutions.csv` | `aicte_code,name,state,parent_trust` (about 12% share one of three parent trusts) |
| `intake.csv` | `shared/csv/intake-template.csv` |
| `admissions.csv` | `shared/csv/admissions-template.csv` |
| `ground_truth.csv` | `record_id,anomaly_type,details` |

`record_id` is either `R0000123` (the 123rd data row of `admissions.csv`) or, for intake overruns, the pool key `aicte_code|programme_code|academic_year|seat_pool`.

## Anomaly catalogue

| Type | How it is planted | Should be caught by |
| --- | --- | --- |
| `intake_overrun` | About 1 in 30 regular pools is filled to approved seats and then 10–25% past it | `INTAKE_OVERRUN` at commit (Seat Ledger); engine `cap_filling` |
| `dup_cross_institution` | A student's APAAR, name, DOB and contacts are copied into a free seat at another institution | `DUP_CROSS_INSTITUTION` |
| `typo_duplicate` | Same DOB, guardian and state at another institution, name misspelled by a dropped, swapped or doubled letter; APAAR is new (half) or blank with opt-out (half) | `FUZZY_MATCH_CANDIDATE` (engine Blind Match) |
| `shared_contact_cluster` | 6–12 students in one pool get the same phone and email | `SHARED_CONTACT_CLUSTER`; engine `shared_contact_clusters` |
| `backdated_entry` | Admission date moved to March–May 2026, before the July–September window, and mode set to `management` | `BACKDATED_ENTRY`; engine `backdating` |
| `opted_out` | APAAR blanked, `apaar_opt_out=true`, provisional ID `PROV-<aicte_code>-NNNN` | `APAAR_OPTED_OUT` (info only, never an error) |

Duplicates only go into pools with free seats, so the only overruns are the planted ones.

Owner: Dev C.
