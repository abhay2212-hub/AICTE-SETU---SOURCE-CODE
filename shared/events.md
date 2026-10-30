<!-- Owner: Dev B -->
# Realtime events

All events are broadcast on the Supabase Realtime channel **`platform`** (public Broadcast, sent by the backend through the Realtime REST broadcast endpoint). Each message has an `event` name and a JSON `payload`. Timestamps are ISO 8601 UTC.

Payloads carry IDs, counts and statuses only: never names, contacts, APAAR IDs or free-text notes. Fetch details through the API.

## `batch.committed`

```json
{
  "batch_id": "30000000-0000-4000-8000-000000000001",
  "institution_id": "10000000-0000-4000-8000-000000000003",
  "rows_committed": 70,
  "rows_rejected": 4,
  "committed_at": "2026-09-02T10:15:00Z"
}
```

## `review_case.created`

```json
{
  "case_id": "60000000-0000-4000-8000-000000000001",
  "kind": "intake_overrun",
  "institution_id": "10000000-0000-4000-8000-000000000003",
  "status": "open",
  "created_at": "2026-09-02T10:15:01Z"
}
```

## `review_case.updated`

Sent when a case is resolved, when a later commit refreshes an open overrun case, and when a withdrawal brings an overrun pool back within capacity (a note is added; the case stays open).

```json
{
  "case_id": "60000000-0000-4000-8000-000000000001",
  "status": "confirmed",
  "updated_at": "2026-09-03T08:00:00Z"
}
```

## `admission.status_changed`

```json
{
  "admission_id": "50000000-0000-4000-8000-000000000004",
  "student_id": "40000000-0000-4000-8000-000000000004",
  "from": "submitted",
  "to": "student_disputed",
  "changed_at": "2026-09-04T12:30:00Z"
}
```

Sent when an admission is withdrawn (`to: "withdrawn"`), a student confirms or disputes it (`student_confirmed`, `student_disputed`), or `POST /admin/admissions/mark-no-response` marks it `no_response`.

## `submission_window.updated`

Sent when an `aicte_admin` creates, moves or locks the submission window of an academic year. `state` is `not_open`, `open`, `closed` or `locked` at the time of the change.

```json
{
  "window_id": "a0000000-0000-4000-8000-000000000001",
  "academic_year": "2026-27",
  "state": "locked",
  "updated_at": "2026-12-31T18:30:00Z"
}
```

## `edit_request.decided`

Sent when an `aicte_admin` approves or rejects an edit request. An approved `withdrawal` request is followed by `admission.status_changed`.

```json
{
  "edit_request_id": "70000000-0000-4000-8000-000000000001",
  "admission_id": "50000000-0000-4000-8000-000000000004",
  "status": "approved",
  "decided_at": "2026-09-03T12:00:00Z"
}
```

## `audit.tamper_detected`

```json
{
  "first_broken_index": 1287,
  "checked": 5402,
  "detected_at": "2026-09-05T06:00:00Z"
}
```
