<!-- Owner: Dev B. Consumed by Dev E (Telegram webhook, student portal). -->
# Student responses: confirm or dispute an admission

A student answers "Is this you?" for one admission record, by Telegram or on the student portal. Dev E's webhook and portal backend call one internal endpoint. Students never call it directly from the browser.

## Endpoint

`POST /internal/student-responses`

| Header | Value |
| --- | --- |
| `X-Internal-Token` | Equal to the backend's `INTERNAL_API_TOKEN`. If that is empty, the backend accepts `TELEGRAM_WEBHOOK_SECRET` instead. |
| `Content-Type` | `application/json` |

### Request

```json
{
  "admission_id": "50000000-0000-4000-8000-000000000004",
  "response": "disputed",
  "channel": "telegram"
}
```

| Field | Values |
| --- | --- |
| `admission_id` | UUID of the admission (from `GET /students/me/records` or the Telegram link) |
| `response` | `confirmed` or `disputed` |
| `channel` | `telegram` or `portal` |

### Response `200`

```json
{
  "admission_id": "50000000-0000-4000-8000-000000000004",
  "status": "student_disputed",
  "changed": true,
  "review_case_id": "60000000-0000-4000-8000-000000000003"
}
```

| Field | Meaning |
| --- | --- |
| `status` | The admission status now: `student_confirmed` or `student_disputed` |
| `changed` | `false` when this response was already recorded (see idempotency) |
| `review_case_id` | The open `dispute` review case for this admission, or `null` |

## What happens

- `confirmed` sets the admission to `student_confirmed`.
- `disputed` sets `student_disputed` and opens a `dispute` review case with evidence `{admission_id, institution_id, programme, academic_year, channel}`. There is at most one open dispute case per admission.
- Each change writes an audit event (actor `student:<student_id>`) and broadcasts `admission.status_changed` on the Realtime channel `platform`. A new dispute also broadcasts `review_case.created`.
- A student can change their answer: `confirmed` → `disputed` opens a case. `disputed` → `confirmed` updates the status and leaves the case open for the reviewer.
- `submitted` and `no_response` admissions accept either response.

## Idempotency

Sending the same `response` for the same admission again changes nothing. There is no new audit event, no broadcast and no second case. The reply has `changed: false` and the current `review_case_id`. The `channel` of a repeat is ignored. Telegram retries and double taps are safe.

## Errors

The `detail` body is `{"code": "...", "message": "..."}`, except for 422.

| HTTP | `detail.code` | When |
| --- | --- | --- |
| 401 | `INVALID_INTERNAL_TOKEN` | `X-Internal-Token` missing or wrong |
| 503 | `INTERNAL_TOKEN_UNCONFIGURED` | Neither `INTERNAL_API_TOKEN` nor `TELEGRAM_WEBHOOK_SECRET` is set |
| 404 | `ADMISSION_NOT_FOUND` | No admission with that id |
| 409 | `ADMISSION_WITHDRAWN` | The admission was withdrawn; no response is recorded |
| 422 | (FastAPI validation list) | `response` or `channel` not one of the allowed values, or a field missing |

## Related

- `POST /admin/admissions/mark-no-response` (`aicte_admin`), body `{"older_than_days": 14}`. It sets `no_response` on every active `submitted` admission committed more than N days ago and broadcasts `admission.status_changed` for each one.
- While the `admissions` domain is on fixtures (not in `REAL_DOMAINS`), the endpoint answers from the mock admissions and stores nothing.

## Example (PowerShell)

```powershell
$token = "replace-with-internal-token"
$body = '{"admission_id":"50000000-0000-4000-8000-000000000004","response":"confirmed","channel":"portal"}'
curl.exe -s -X POST "http://localhost:8000/internal/student-responses" `
  -H "X-Internal-Token: $token" `
  -H "Content-Type: application/json" `
  --data-raw $body
```

Python (bot side, `httpx`):

```python
httpx.post(
    f"{API_URL}/internal/student-responses",
    json={"admission_id": admission_id, "response": "disputed", "channel": "telegram"},
    headers={"X-Internal-Token": INTERNAL_API_TOKEN},
    timeout=5,
)
```
