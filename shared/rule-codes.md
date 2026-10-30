<!-- Owner: Dev B. Mirrored exactly by backend/app/core/rule_codes.py. -->
# Validation rule codes

Severity meanings: `error` blocks commit of the row; `warning` is shown but does not block; `review` opens or feeds a review case; `info` is informational only.

| Code | Severity | Meaning |
| --- | --- | --- |
| `REQUIRED_FIELD_MISSING` | error | A required column is blank. |
| `APAAR_MISSING` | error | `apaar_id` is blank and the student has not opted out. |
| `APAAR_FORMAT` | error | `apaar_id` is not exactly 12 digits. |
| `APAAR_OPTED_OUT` | info | Student opted out of APAAR; a provisional ID is used instead. Never an error. |
| `DUP_IN_BATCH` | error | The same APAAR or provisional ID appears more than once in this batch. |
| `DUP_CROSS_INSTITUTION` | review | The APAAR ID is already enrolled at another institution for the same academic year. |
| `FUZZY_MATCH_CANDIDATE` | review | Blind Match found a likely duplicate identity with a different or missing APAAR. |
| `PROGRAMME_UNKNOWN` | error | `programme_code` is not an approved programme of the institution. |
| `POOL_UNKNOWN` | error | `seat_pool` is not one of `regular`, `tfw`, `fn_oci_pio`, `nri`. |
| `DATE_INVALID` | error | A date is not a valid `YYYY-MM-DD` date. |
| `ADMISSION_AFTER_CUTOFF` | warning | `admission_date` is after the AICTE cutoff for the academic year. |
| `BACKDATED_ENTRY` | review | `admission_date` is well before the upload and inconsistent with the batch timeline. |
| `FN_WITHOUT_NATIONALITY` | error | `fn_status=true` but `nationality` is India or blank. |
| `OCI_INCONSISTENT` | warning | OCI/PIO status conflicts with nationality or seat pool. |
| `NRI_POOL_MISMATCH` | warning | `nri_category` and `seat_pool=nri` disagree. |
| `AGE_IMPLAUSIBLE` | warning | Age at admission is outside the plausible range for the programme. |
| `QUALIFYING_BELOW_NORM` | warning | `qualifying_exam_pct` is below the AICTE minimum for the programme and category. |
| `INTAKE_OVERRUN` | review | Committing the row would exceed the approved seats in its pool. |
| `SHARED_CONTACT_CLUSTER` | review | The hashed phone or email is shared by an unusually large group of students. |
