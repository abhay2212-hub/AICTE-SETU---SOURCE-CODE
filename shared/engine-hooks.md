<!-- Owner: Dev B. Mirrored by backend/app/services/validation.py (engine hooks section). -->
# Engine hook contract

What the backend upload hook sends to Dev A's engine and what it accepts back. The hook runs during upload validation and again at commit time (`app.services.validation.engine_findings`). It never lets an engine bug break an upload: `NotImplementedError` skips that hook quietly, any other exception skips it and logs one line.

## 1. Functions the hook calls

| Call | Arguments | Expected return |
| --- | --- | --- |
| `engine.signals.rules.eligibility(rows)` | `rows`: list of row dicts (section 2) | `list[Signal]` (section 3) |
| `engine.signals.rules.backdating(rows)` | the same `rows` list | `list[Signal]` (section 3) |
| `engine.blind_match.encoder.encode_identity(fields, secret, bits=1024)` | `fields`: `dict[str, str]`; `secret`: `bytes`; `bits` passed as a keyword. `k` is not passed. | `bytes` of length `bits // 8` (128) |
| `engine.blind_match.encoder.dice(a, b)` | two encodings from `encode_identity` | `float` from 0 to 1 |

**Blocking and pairing for Blind Match are done by the backend, not by `engine.blind_match.linkage.find_candidates`.** The hook does not call `find_candidates` and does not build `EncodedRecord` objects. Dev A may keep `find_candidates` for engine-side analytics, but upload findings never depend on it.

The hook calls `eligibility` and `backdating` once per batch, `encode_identity` once per row that has a block partner (section 4), and `dice` once per compared pair. Engine functions must be pure: no network, no database, no writing files, no logging of row contents.

## 2. Row dicts passed to `eligibility` and `backdating`

One dict per uploaded data row, in upload order, including rows that also have validation errors. Every key below is always present.

| Key | Type | Notes |
| --- | --- | --- |
| `row_number` | `int` | 1-based data row number (header not counted). The same numbering as validation findings and `batch_rows`. |
| `upload_date` | `str` | ISO date `YYYY-MM-DD`: today's date in UTC when the hook runs. The same value on every row of a call. |
| `institution_aicte_code` | `str \| None` | Upper-cased, e.g. `1-9999003`. |
| `programme_code` | `str \| None` | Upper-cased, e.g. `UG-CSE`. |
| `academic_year` | `str \| None` | e.g. `2026-27`. |
| `student_name` | `str \| None` | Title-cased, spaces collapsed. |
| `dob` | `str \| None` | ISO date. `None` if blank or not a valid date. |
| `gender` | `str \| None` | Lower-cased. |
| `category` | `str \| None` | Lower-cased: `general`, `ews`, `obc`, `sc`, `st` (other values possible on rows with errors). |
| `pwd` | `bool \| None` | |
| `apaar_id` | `str \| None` | Spaces removed. May be malformed on rows with an `APAAR_FORMAT` error. **SIMULATED** APAAR IDs only. |
| `apaar_opt_out` | `bool \| None` | |
| `provisional_id` | `str \| None` | Upper-cased. |
| `nationality` | `str \| None` | Upper-cased. |
| `oci_status` | `bool \| None` | |
| `fn_status` | `bool \| None` | |
| `nri_category` | `bool \| None` | |
| `seat_pool` | `str \| None` | Lower-cased: `regular`, `tfw`, `fn_oci_pio`, `nri` (other values possible on rows with errors). |
| `admission_mode` | `str \| None` | Lower-cased: `cap`, `management`, `lateral`, `spot`. |
| `admission_date` | `str \| None` | ISO date. `None` if blank or not a valid date. |
| `qualifying_exam` | `str \| None` | |
| `qualifying_exam_pct` | `float \| None` | 0 to 100, two decimals. `None` if blank or out of range. |
| `domicile_state` | `str \| None` | |
| `contact_phone` | `str \| None` | Already hashed: `hmac:<hex>`. Never a raw number. |
| `contact_email` | `str \| None` | Already hashed: `hmac:<hex>`. Never a raw address. |
| `guardian_name` | `str \| None` | Title-cased. |

Rules for engines:

- Dates are ISO strings, never `date` objects. Parse them with `date.fromisoformat`.
- Any field except `row_number` and `upload_date` may be `None`. Engines must skip or tolerate `None`; never stringify it (`str(None)` gives `"None"`, which is a wrong value, not a blank).
- Do not mutate the dicts or the list.

## 3. Signals the hook accepts

`eligibility` and `backdating` return a list of `engine.types.Signal` (a plain dict with the same keys is also accepted). The hook turns a signal into one backend finding per listed row only if **all** of these hold:

| Field | Accepted values |
| --- | --- |
| `code` | `QUALIFYING_BELOW_NORM` or `BACKDATED_ENTRY` (either hook may return either code) |
| `severity` | `warning` or `review` |
| `evidence["row_numbers"]` | non-empty list of `int` values taken from the input `row_number`s |
| `evidence["reason"]` | short human-readable string, e.g. `"pct 41.0 below UG general minimum 45"`. Optional; the hook uses a generic message when it is missing. |
| `institution_id` | anything; ignored by the hook |

- The finding's rule code is the signal's `code`. Its severity comes from `shared/rule-codes.md` (`QUALIFYING_BELOW_NORM` is a warning, `BACKDATED_ENTRY` is review), not from the signal.
- The finding's message and evidence carry only `reason` (truncated to 200 characters). Other evidence keys are dropped, so put nothing personal in `reason`: no names, dates of birth, contacts or APAAR IDs.
- One row gets at most one finding per code, however many signals list it.
- Anything else is ignored: an unknown code, an unknown severity, a missing or empty `row_numbers`, a row number that is not an `int` or not in the batch. The hook logs one warning per batch with counts per reason, never row contents.

## 4. Blind Match inputs

For each row with both `student_name` and a valid `dob` that shares its DOB block with at least one other row, the backend calls:

```python
encode_identity(
    {"student_name": "Aarav Sharma", "dob": "2008-03-14", "guardian_name": "Rakesh Sharma"},
    secret,          # BLIND_MATCH_SECRET as UTF-8 bytes, always passed explicitly
    bits=1024,
)
```

- `bits` is fixed at 1024 by the backend, so every encoding is 128 bytes. `k` (hash positions per bigram) is chosen by the engine: the backend never passes it, so the engine's own default applies. Changing that default changes every encoding, so keep it stable within a deployment.

- Identity fields: `student_name`, `dob` (ISO) and `guardian_name`. `guardian_name` is left out of `fields` when it is blank. All values are `str`, never `None`. The engine does its own normalisation (case, accents, punctuation).
- `secret` is always `BLIND_MATCH_SECRET` from backend settings, passed explicitly. Engines must not read environment variables or fall back to a default key. If `BLIND_MATCH_SECRET` is empty the backend skips Blind Match for the batch and logs one warning; `encode_identity` is never called with an empty key.
- Blocking (backend): rows are grouped by `HMAC-SHA256(BLIND_MATCH_SECRET, "dob:" + dob_iso)`, so only rows with exactly the same date of birth are compared. Each block is capped at `BLIND_MATCH_MAX_BLOCK` rows (default 200); extra rows are left out and the backend logs that a block was truncated.
- Pairing (backend): within a block every pair is compared with `dice`, except pairs where both rows have a valid 12-digit APAAR ID (different IDs are different people; equal IDs are already `DUP_IN_BATCH`) and pairs with the same APAAR or provisional ID.
- Threshold: a pair with `dice(a, b) >= MATCH_THRESHOLD` (setting `match_threshold`, default `0.85`) raises `FUZZY_MATCH_CANDIDATE` on the later row, with evidence `{"other_row": <earlier row_number>, "dice": <rounded to 3 places>}`.
- `encode_identity` must return `bytes` of length `bits // 8` (128). A row whose encoding has another type or length is left out of matching and counted in the batch warning.

## 5. Testing against this contract

Backend unit tests replace the engine functions with fakes that follow this contract (`backend/tests/fake_engine.py`). A minimal version:

```python
import hashlib
import hmac

from engine.types import Signal


def fake_eligibility(rows):
    low = [r["row_number"] for r in rows if (r["qualifying_exam_pct"] or 100) < 45]
    if not low:
        return []
    return [Signal("QUALIFYING_BELOW_NORM", "batch", "warning",
                   {"row_numbers": low, "reason": "pct below AICTE minimum"})]


def fake_encode_identity(fields, secret, bits=1024, k=20):
    assert secret, "secret must be passed explicitly"
    bloom = 0
    for name, value in fields.items():
        text = f" {' '.join(value.lower().split())} "
        for i in range(len(text) - 1):
            digest = hmac.new(secret, f"{name}:{text[i:i + 2]}".encode(), hashlib.sha256).digest()
            h1, h2 = int.from_bytes(digest[:8]), int.from_bytes(digest[8:16]) | 1
            for j in range(k):
                bloom |= 1 << ((h1 + j * h2) % bits)
    return bloom.to_bytes(bits // 8, "big")


def test_low_pct_becomes_a_finding(monkeypatch):
    import engine.blind_match.encoder as encoder
    import engine.signals.rules as rules

    monkeypatch.setattr(rules, "eligibility", fake_eligibility)
    monkeypatch.setattr(encoder, "encode_identity", fake_encode_identity)
    # build rows, call validate_rows(rows, ctx, blind_match_secret="test-secret")
    # and assert QUALIFYING_BELOW_NORM on the low row only
```

Dev A can check the engine side with the same shapes: feed `eligibility` and `backdating` row dicts built exactly as in section 2 (including `None` values and ISO strings), assert every returned signal passes the section 3 checks, and assert `encode_identity` returns `bits // 8` bytes, is deterministic for the same secret, and changes when the secret changes.
