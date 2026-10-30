<!-- Owner: Dev B. Consumed by Dev X (student portal, verifier page) and Dev A (frontend/src/lib/credential-verify.ts). Mirrored by backend/app/services/credentials.py. -->
# Student credentials

A student shares chosen facts about one admission with one verifier (an employer, a scholarship cell) as a signed QR code. The verifier checks it offline with the platform's public key, or online with `POST /credentials/verify`. The APAAR ID is never in a credential.

## 1. Signed payload

```json
{
  "v": 1,
  "id": "92000000-0000-4000-8000-000000000001",
  "iss": "apaar-integrity-platform",
  "sub": "c15bf3f2cddbcb7b3472a0fa60b361d30193b088abf112d2136f4987ce76a55a",
  "aud": "Acme Infotech",
  "claims": {
    "academic_year": "2026-27",
    "enrolment_status": "student_confirmed",
    "institution": "Meghdoot Institute of Engineering",
    "programme": "B.Tech Computer Science and Engineering"
  },
  "iat": 1789027200,
  "exp": 1789632000,
  "nonce": "00000000000000000000000000000001"
}
```

| Key | Type | Meaning |
| --- | --- | --- |
| `v` | integer | Format version, always `1`. Reject anything else. |
| `id` | string (UUID) | Credential ID. Used for revocation. |
| `iss` | string | Always `apaar-integrity-platform`. Reject anything else. |
| `sub` | string (64 hex) | Per-audience pseudonym of the student (section 3). |
| `aud` | string | Audience text the student typed (verifier name), as entered. |
| `claims` | object of string → string | Only the claims the student chose (section 4). |
| `iat` | integer | Issued at, Unix seconds (UTC). |
| `exp` | integer | Expires at, Unix seconds (UTC). Invalid at and after this second. |
| `nonce` | string (32 hex) | 16 random bytes, so two otherwise equal credentials differ. |

Every value is a string or an integer. There are no floats, booleans or nulls, so the canonical form is the same in Python and JavaScript.

## 2. Canonical bytes and signature

- **Canonical bytes**: the payload as JSON with keys sorted (recursively, by code point), no whitespace (`,` and `:` separators), non-ASCII characters written as UTF-8 (not `\u` escapes), then encoded as UTF-8. Python: `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()`. JavaScript: `JSON.stringify` of a copy with keys inserted in sorted order, then `TextEncoder`.
- **Signature**: Ed25519 over the canonical bytes. The signing key is `CREDENTIAL_SIGNING_KEY`, a 32-byte seed written as 64 hex characters (backend secret).
- The verifier re-canonicalises the payload it decoded from the QR text and checks the signature over those bytes. It never verifies the bytes of the QR envelope itself.

Canonical bytes of the example:

```text
{"aud":"Acme Infotech","claims":{"academic_year":"2026-27","enrolment_status":"student_confirmed","institution":"Meghdoot Institute of Engineering","programme":"B.Tech Computer Science and Engineering"},"exp":1789632000,"iat":1789027200,"id":"92000000-0000-4000-8000-000000000001","iss":"apaar-integrity-platform","nonce":"00000000000000000000000000000001","sub":"c15bf3f2cddbcb7b3472a0fa60b361d30193b088abf112d2136f4987ce76a55a","v":1}
```

## 3. Pseudonym

`sub = hex(HMAC-SHA256(PSEUDONYM_SECRET, student_id + ":" + normalised_audience))`

- `student_id` is the student's UUID in lower case.
- `normalised_audience` is the audience with whitespace runs collapsed to one space, trimmed, and lower-cased. `"  Acme   Infotech "` and `"acme infotech"` give the same pseudonym.
- Each audience sees a different pseudonym for the same student, so two verifiers cannot link their credentials. The same audience always sees the same pseudonym.
- The example uses the test secret `test-pseudonym-secret` and student `40000000-0000-4000-8000-000000000001`.

## 4. Claims

| Claim | Value |
| --- | --- |
| `enrolment_status` | The admission's status: `submitted`, `student_confirmed`, `student_disputed` or `no_response` |
| `institution` | Institution name |
| `programme` | Programme name, e.g. `B.Tech Computer Science and Engineering` |
| `academic_year` | e.g. `2026-27` |

Only these four claims are allowed. **The APAAR ID is never a claim** and never appears anywhere in the payload or QR text. The values come from one active admission of the student: the one named by `admission_id` in the request, or else the most recent.

## 5. Expiry

The student picks one of three:

| `expiry` | Lifetime |
| --- | --- |
| `15m` | 15 minutes |
| `1d` | 1 day |
| `7d` | 7 days |

`exp = iat + lifetime`.

**Enrolment certificates (internal).** The backend also issues credentials for enrolment certificates (`GET /certificates/{student_id}?format=pdf`, `GET /students/me/certificate`). These use the same format with audience `enrolment-certificate`, all four claims and a **180-day** lifetime. Students cannot request that lifetime: `POST /credentials` still accepts only `15m`, `1d` and `7d`. The certificate ID is the credential ID, so revoking the credential revokes the certificate. Verifiers need no change.

## 6. QR text

`qr_text = base64url_no_padding(UTF-8 JSON of {"payload": <payload object>, "sig": <base64 signature>})`

- `sig` is standard base64 **with** padding (88 characters for 64 bytes).
- The outer encoding is base64url (`-` and `_`) **without** padding. Decoders must accept it with or without `=` padding.
- The envelope JSON itself needs no particular key order or whitespace.

Example QR text (the payload above, signed with the test seed):

```text
eyJwYXlsb2FkIjp7InYiOjEsImlkIjoiOTIwMDAwMDAtMDAwMC00MDAwLTgwMDAtMDAwMDAwMDAwMDAxIiwiaXNzIjoiYXBhYXItaW50ZWdyaXR5LXBsYXRmb3JtIiwic3ViIjoiYzE1YmYzZjJjZGRiY2I3YjM0NzJhMGZhNjBiMzYxZDMwMTkzYjA4OGFiZjExMmQyMTM2ZjQ5ODdjZTc2YTU1YSIsImF1ZCI6IkFjbWUgSW5mb3RlY2giLCJjbGFpbXMiOnsiYWNhZGVtaWNfeWVhciI6IjIwMjYtMjciLCJlbnJvbG1lbnRfc3RhdHVzIjoic3R1ZGVudF9jb25maXJtZWQiLCJpbnN0aXR1dGlvbiI6Ik1lZ2hkb290IEluc3RpdHV0ZSBvZiBFbmdpbmVlcmluZyIsInByb2dyYW1tZSI6IkIuVGVjaCBDb21wdXRlciBTY2llbmNlIGFuZCBFbmdpbmVlcmluZyJ9LCJpYXQiOjE3ODkwMjcyMDAsImV4cCI6MTc4OTYzMjAwMCwibm9uY2UiOiIwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMSJ9LCJzaWciOiJOTFhCcTlrbVlCd01yN1BFWnM4MHJHMWdhbDBuWFU2bnBnN3lpVVA5NUs3TjFJRERsT1JtNWpTUmNpZVhmM3RoVk1PSWVUMWZ6Q2xoaUZBcmhnT2pBQT09In0
```

Its signature: `NLXBq9kmYBwMr7PEZs80rG1gal0nXU6npg7yiUP95K7N1IDDlORm5jSRcieXf3thVMOIeT1fzClhiFArhgOjAA==`

## 7. Public key

`GET /credentials/public-key` (no login):

```json
{
  "algorithm": "Ed25519",
  "key_id": "56475aa75463474c",
  "public_key_b64": "A6EHv/POEL4dcN0Y50vAmWfk1jCbpQ1fHdyGZBJVMbg="
}
```

- `public_key_b64` is standard base64 of the raw 32-byte Ed25519 public key.
- `key_id` is the first 16 hex characters of SHA-256 of those 32 bytes. It is informational; the payload does not carry it.
- The values above are the **test** key (seed `000102…1f`). Fixture mode serves this key. A real deployment serves the key derived from `CREDENTIAL_SIGNING_KEY`.

## 8. Verifying (offline or in the browser)

In this order, stopping at the first failure:

1. Decode the QR text and parse the envelope. On failure: `malformed`.
2. Check the Ed25519 signature over the canonical payload bytes with the public key. On failure: `bad_signature`.
3. `v` must be `1` and `iss` must be `apaar-integrity-platform`. On failure: `unsupported`.
4. `now >= exp`: `expired`.
5. `id` is in `GET /credentials/revocations` (`revoked[].credential_id`): `revoked`.
6. Otherwise valid: show `claims`, `aud` and the expiry.

Test vectors for all of this (valid, tampered, expired, revoked, public key, canonical bytes) are under `credentials` in `shared/test-vectors.json`. Each case has a `verify_at` Unix time to use as "now" and the `revoked_ids` to treat as revoked. They are signed with the fixed **test** seed, never the production key. Regenerate with `uv run python -m scripts.credential_vectors` in `backend/`.

## 9. Endpoints

All student endpoints act on the signed-in student only. Fixture mode (domain not in `REAL_DOMAINS`) serves fixtures. Fixture-mode credentials are signed live with the test seed, so they verify against the fixture public key.

| Method and path | Who | Body | Returns |
| --- | --- | --- | --- |
| `POST /credentials` | student | `{"claims": [...], "audience": "Acme Infotech", "expiry": "7d", "admission_id": null}` | `201 {id, qr_text, expires_at, claims}` |
| `POST /credentials/{id}/revoke` | the owning student | `{"reason": "..."}` | `{credential_id, reason, revoked_at}`. Repeating it is a no-op. Another student's credential is `404`. |
| `GET /credentials/revocations` | anyone | | `{updated_at, revoked: [{credential_id, reason, revoked_at}]}` |
| `GET /credentials/public-key` | anyone | | section 7 |
| `POST /credentials/verify` | anyone (verifier or no login) | `{"qr_text": "..."}` | `{valid, reason?, claims?, expires_at?}` |

- `POST /credentials` also writes an audit event (`credential.issued`) and an access-log entry for the student: purpose `credential issued for <audience>`.
- `POST /credentials/verify` checks signature, expiry and revocation on the server. When the signature is good it adds an access-log entry for the student: accessor = the payload's `aud`, role `verifier`, purpose `credential verification`, fields = the claim names. Nothing else about the student is revealed. `reason` is one of `malformed`, `bad_signature`, `unsupported`, `expired`, `revoked`. `claims` is present only when valid.
- `409 NO_ACTIVE_ADMISSION` when the student has no active admission (or `admission_id` is not one of theirs).
- **Deprecated aliases**, kept so the current student page keeps working: the request may send `verifier_id` (as `audience`), `fields` (as `claims`; `status` means `enrolment_status`) and `expires_in_days` (`1` → `1d`, `7` → `7d`). The response also carries `credential_id` (= `id`) and `qr_payload` (= `qr_text`). New code should use the new names. The aliases will be removed later.

## 10. Demo student (MOCK_MODE=true)

While `MOCK_MODE=true`, `X-Demo-Role: student` resolves to the designated demo student:

- **Fixture mode** (`students` / `credentials` not real): student `40000000-0000-4000-8000-000000000001` from the fixtures.
- **Real mode**: the student with `students.is_demo = true`. `scripts/load_demo.py` marks one clean Meghdoot Institute student with an admission still in status `submitted`, so Confirm and Dispute can be shown. `404 DEMO_STUDENT_NOT_FOUND` if none is marked.
- The optional header `X-Demo-Student: <student id>` overrides it, in either mode. It is honoured only while `MOCK_MODE=true`.
- With `MOCK_MODE=false` a student's Supabase token must carry `app_metadata.student_id`; otherwise student endpoints return `403`.

## 11. Other student endpoints

| Method and path | Body | Notes |
| --- | --- | --- |
| `GET /students/me/records` | | `{student, admissions}`. `student.apaar_id` and `student.apaar_id_masked` are both masked (`XXXX-XXXX-1234`). Admissions include withdrawn ones, newest first. |
| `POST /students/me/admissions/{id}/response` | `{"response": "confirmed" \| "disputed"}` | Same behaviour as `shared/student-responses.md` with `channel = "portal"`. Another student's admission is `404`. |
| `GET /students/me/consents` | | Newest first. |
| `POST /students/me/consents` | `{"verifier_id", "verifier_name"?, "purpose", "fields", "expires_in_days", "action": "grant" \| "withdraw"}` | `grant` (default) creates the consent, or renews the active one with the same `verifier_id` and `purpose`. `withdraw` sets `revoked_at` on it (`404` if there is none). Audit event either way. |
| `GET /students/me/access-log` | | Newest first, at most 200. |

**APAAR sharing opt-out**: `purpose: "apaar_sharing"` is reserved. It records whether the student allows their APAAR ID to be shared with the (**SIMULATED**) APAAR / DigiLocker systems. `verifier_id` and `verifier_name` are set by the server to `apaar-simulated` and `APAAR (SIMULATED)`. `action: "withdraw"` records the opt-out even when no grant exists, so the student's choice is always on file.
