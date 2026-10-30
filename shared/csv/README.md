<!-- Owner: Dev B -->
# CSV data dictionary

Two upload formats. Both files are UTF-8, comma-separated, with exactly the header rows in the templates.

Conventions:

- Dates are `YYYY-MM-DD`.
- Academic year is `2026-27` style (`YYYY-YY`).
- Booleans are `true|false` (lowercase).
- `seat_pool` is one of `regular|tfw|fn_oci_pio|nri`.
- `admission_mode` is one of `cap|management|lateral|spot`.
- Contact fields (`contact_phone`, `contact_email`) are hashed on ingest and never stored raw.
- Never put Aadhaar numbers in any column.

## admissions-template.csv

| Column | Type | Required | Allowed values / format | Example |
| --- | --- | --- | --- | --- |
| `institution_aicte_code` | string | required | AICTE permanent institute code | `1-9999001` |
| `programme_code` | string | required | Programme code known to the platform for that institution | `UG-CSE` |
| `academic_year` | string | required | `YYYY-YY` | `2026-27` |
| `student_name` | string | required | Full name as on qualifying-exam records | `Aarav Sharma` |
| `dob` | date | required | `YYYY-MM-DD` | `2008-03-14` |
| `gender` | enum | required | `male|female|transgender` | `female` |
| `category` | enum | required | `general|ews|obc|sc|st` | `obc` |
| `pwd` | boolean | required | `true|false` | `false` |
| `apaar_id` | string | conditional | Exactly 12 digits. Blank only when `apaar_opt_out=true` | `999912345678` |
| `apaar_opt_out` | boolean | required | `true|false` | `false` |
| `provisional_id` | string | conditional | Required when `apaar_opt_out=true`; institution-issued, unique | `PROV-1-9999001-0001` |
| `nationality` | string | required | Country name or ISO 3166 alpha-2 | `IN` |
| `oci_status` | boolean | required | `true|false`; `true` for OCI/PIO card holders | `false` |
| `fn_status` | boolean | required | `true|false`; `true` for foreign nationals | `false` |
| `nri_category` | boolean | required | `true|false`; `true` when admitted under NRI quota | `false` |
| `seat_pool` | enum | required | `regular|tfw|fn_oci_pio|nri` | `regular` |
| `admission_mode` | enum | required | `cap|management|lateral|spot` | `cap` |
| `admission_date` | date | required | `YYYY-MM-DD` | `2026-08-05` |
| `qualifying_exam` | string | required | Name of qualifying exam | `JEE Main` |
| `qualifying_exam_pct` | number | required | 0–100, up to 2 decimals | `87.40` |
| `domicile_state` | string | required | Indian state or union territory name | `Maharashtra` |
| `contact_phone` | string | optional | 10-digit Indian mobile, with or without `+91`; hashed on ingest | `+919800000001` |
| `contact_email` | string | optional | Email address; lowercased and hashed on ingest | `student@example.com` |
| `guardian_name` | string | optional | Full name | `Rakesh Sharma` |

## intake-template.csv

| Column | Type | Required | Allowed values / format | Example |
| --- | --- | --- | --- | --- |
| `institution_aicte_code` | string | required | AICTE permanent institute code | `1-9999001` |
| `programme_code` | string | required | Programme code | `UG-CSE` |
| `academic_year` | string | required | `YYYY-YY` | `2026-27` |
| `seat_pool` | enum | required | `regular|tfw|fn_oci_pio|nri` | `regular` |
| `approved_seats` | integer | required | `>= 0` | `60` |
| `rule_version` | string | required | Version of the AICTE approval handbook rule set used to compute the split | `APH-2026-27-v1` |
