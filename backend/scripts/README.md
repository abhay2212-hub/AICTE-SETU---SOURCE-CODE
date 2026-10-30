<!-- Owner: Dev B -->
# backend/scripts

Run every script from `backend/`. They read `backend/.env` and never print its values.

| Script | Purpose |
| --- | --- |
| `load_demo.py` | Reset and load the demo dataset through the real services |
| `realtime_probe.py` | Print every broadcast on the Realtime channel `platform` for N seconds |
| `tamper_demo.py` | Break and restore one audit event to demo `/audit/verify` |
| `export_contracts.py` | Write `shared/openapi.json` and `shared/schemas/` |
| `demo_live_reset.py` | Undo a live upload of `deck/demo/shadow-late-batch.csv` so it can be uploaded again (`--yes` required) |
| `blind_match_scan.py` | Cross-institution Blind Match rescan of every committed student (no reset; safe to rerun) |
| `credential_vectors.py` | Regenerate the `credentials` test vectors in `shared/test-vectors.json` (fixed test seed) |

## Demo dataset: `load_demo.py`

```powershell
uv run python -m scripts.load_demo --reset --yes                  # clean slate, default sizes
uv run python -m scripts.load_demo                                # load again without deleting
uv run python -m scripts.load_demo --institutions 50 --students 10000 --seed 7
uv run python -m scripts.load_demo --source ..\datagen\out        # use existing datagen output
```

| Flag | Default | Meaning |
| --- | --- | --- |
| `--reset` | off | Delete demo data first. Refused without `--yes`. |
| `--yes` | off | Confirms `--reset` |
| `--institutions` | 25 | Institutions `datagen` generates (on top of the 3 seed institutions) |
| `--students` | 5000 | Admissions `datagen` generates |
| `--seed` | 42 | Seed for `datagen` and for the scripted seed-institution batches |
| `--workers` | 4 | Institutions loaded at the same time. Only institutions with no APAAR ID in common run in parallel, so findings are the same as with `--workers 1`. |
| `--source` | none | A `datagen` output folder (`institutions.csv`, `intake.csv`, `admissions.csv`). Without it, `datagen/generate.py` runs into a new temp folder outside the repo. |

Needs `DATABASE_URL` and `PSEUDONYM_SECRET`. With `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` set, every commit is also broadcast on `platform`.

### What `--reset --yes` does

1. Prints the row count of every table it touches.
2. Deletes **every** row from `credentials`, `integrity_scores`, `access_log`, `consents`, `telegram_links`, `credential_revocations`, `edit_requests`, `review_cases`, `validation_issues`, `batch_rows`, `admissions`, `batches`, `students` and `audit_events`. Integration-test `TEST-` rows are deleted too.
3. Deletes institutions with `origin = 'load_demo'` (created by an earlier load), with their programmes, seat pools and API keys.
4. Keeps the seed institutions, programmes and seat pools from `supabase/seed.sql`, any other institutions, and `submission_windows`.

The audit chain restarts with a `demo.reset` event.

### What a load does

1. Creates or reopens the **open `2026-27` submission window** (opens 2026-06-01, closes 30 days from now or 2026-12-31, whichever is later) and leaves it open.
2. Creates the generated institutions (`origin = 'load_demo'`), their programmes and their seat pools from `intake.csv`.
3. Uploads and commits **one batch per institution** through `app.services.batches`, acting as that institution's `institution_operator`. Every row goes through ingestion, contact hashing, validation and the Seat Ledger commit, so batches, findings, review cases and audit events are all real. Order: Meghdoot, Narmada Valley and the generated institutions, then Shadow on its own. Institutions whose files share an APAAR ID run one after another in that order. Independent ones run in parallel (`--workers`), because each round trip to the Supabase session pooler can take about 0.4 s. Each transaction also runs in psycopg pipeline mode. The default load took 286 s against the pooler (719 s fully sequential).
4. Runs the cross-institution Blind Match over every student (`app.services.blind_match.scan_all`). Each commit already stored the new students' encodings, so this only compares. It prints the `blind_match` case count, how many of the planted `typo_duplicate` pairs in the `ground_truth.csv` of the datagen output it loaded were found, and whether the scripted Shadow-Narmada pair was found. Precision is true cases over all `blind_match` cases; recall is true cases over the planted plus scripted pairs. Needs `BLIND_MATCH_SECRET`; without it the scan is skipped and says so.
5. Marks the **demo student** (`students.is_demo`): a clean Meghdoot UG-CSE student whose only admission is still `submitted`, with one access-log entry for the upload. `X-Demo-Role: student` resolves to this student while `MOCK_MODE=true` (`shared/credentials.md` section 10).
6. Runs `app.services.integrity.compute_and_save_integrity(conn)` if it exists and prints the 5 lowest-scoring institutions. If it does not exist or raises, it prints `integrity: skipped (<reason>)` and the load carries on.
7. Prints a summary: institutions, students, active admissions, review cases by kind, audit events, Blind Match, the demo student, the `/audit/verify` result, and run time. It also prints a check of the Shadow story. The exit code is 1 if the story or the audit chain is off.

Shadow's two cross-institution duplicates share an APAAR ID with Narmada, so they are one student with two admissions, not a Blind Match pair. Its one Blind Match pair is a separate row: a Narmada CSE student with a one-letter typo in the name (last letter doubled), the same DOB and guardian, and a different valid APAAR ID. The scan opens exactly one `blind_match` case between Shadow and Narmada (`blind_match_with_narmada 1 ok`).

Running a load again without `--reset` is safe. Every file is deterministic for a seed, so it is recognised as already uploaded and its commit returns the stored result.

### The seed institutions

- **Meghdoot Institute of Engineering** (`1-9999001`): 167 clean admissions across UG-CSE and UG-ME, every pool within its seats, no findings.
- **Narmada Valley College of Technology** (`1-9999002`): 163 clean admissions across UG-CSE and UG-ECE. Loaded before Shadow, because two of its CSE students reappear there.
- **Shadow Institute of Technology** (`1-9999003`): scripted, not random. One UG-CSE 2026-27 file of 75 rows:

| What | Rows | Finding | Result |
| --- | --- | --- | --- |
| Over-admission | 71 committed: 62 regular, 3 tfw, 3 fn_oci_pio, 3 nri | `INTAKE_OVERRUN` on the 11 regular rows past seat 51 | **1 `intake_overrun` case, overrun 11**. The programme has 71 admitted against 60 approved (51 + 3 + 3 + 3). |
| Shared contact | 6 | `SHARED_CONTACT_CLUSTER` (review) | flagged rows, committed |
| Late admissions | 3, dated 3, 8 and 14 October 2026 | `ADMISSION_AFTER_CUTOFF` (warning, cutoff 2026-09-30) | committed |
| Cross-institution duplicates | 2 Narmada CSE students, same APAAR, name and DOB | `DUP_CROSS_INSTITUTION` (review) | **2 `signal` cases** |
| Blind Match pair | 1 regular row: another Narmada CSE student, name misspelled by one letter, same DOB and guardian, different APAAR | none at upload | **1 `blind_match` case** with Narmada after the scan |
| APAAR opt-outs | 2, provisional `PROV-1-9999003-0001` and `-0002` | `APAAR_OPTED_OUT` (info, never an error) | committed |
| Hard errors | 4: blank `student_name`, 11-digit APAAR, programme `UG-AERO`, `admission_date` 2026-02-30 | `REQUIRED_FIELD_MISSING`, `APAAR_FORMAT`, `PROGRAMME_UNKNOWN`, `DATE_INVALID` | **rejected**, shown on the upload screen |

The seed gives Shadow UG-CSE 51 regular seats, so 62 regular admissions overrun that pool by 11. The other pools are exactly full, so there is exactly one overrun case. `tests/test_demo_flows.py` checks this batch without a database.

For the demo, fix the 4 rejected rows with `POST /batches/{id}/corrections` (3 of them are UG-CSE, so the overrun case is refreshed). You can also withdraw a Shadow admission and watch the overrun case get a note.

### Synthetic data

All names, dates and contacts are synthetic. Phones are `+9196…` / `+9197…` and emails `@example.com`, and they are hashed before storage. Scripted APAAR IDs are `9999` + block + serial and skip any ID `datagen` used.

## Realtime probe: `realtime_probe.py`

```powershell
uv run python -m scripts.realtime_probe --seconds 60
uv run python -m scripts.realtime_probe --seconds 90 --expect batch.committed review_case.created
```

Prints one JSON line per broadcast and a count per event at the end. The exit code is 1 when an `--expect` event did not arrive. Start it, then commit a batch from the UI, the API or `load_demo.py`.
