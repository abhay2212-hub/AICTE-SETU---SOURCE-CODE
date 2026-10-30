<!-- Owner: Dev B. Consumed by Dev D (institution, AICTE and Blind Match pages). -->
# Realtime client for the frontend

The backend broadcasts on the Supabase Realtime channel **`platform`** (public Broadcast). Event names and payloads are in [`events.md`](events.md). **Payloads carry IDs, counts and statuses only.** They never carry names, contacts, APAAR IDs or notes, so the UI refetches the details from the API when an event arrives.

## Snippet

Tested with `@supabase/supabase-js` 2.118 (the version in `frontend/package.json`). It type-checks under `strict` and received a live broadcast from `app.services.realtime.publish`. Suggested location: `frontend/src/lib/realtime.ts`.

```ts
import type { RealtimeChannel, SupabaseClient } from '@supabase/supabase-js'

// Event names from shared/events.md. Payloads carry IDs, counts and statuses only.
export const PLATFORM_EVENTS = [
  'batch.committed',
  'review_case.created',
  'review_case.updated',
  'admission.status_changed',
  'submission_window.updated',
  'edit_request.decided',
  'audit.tamper_detected',
] as const
export type PlatformEvent = (typeof PLATFORM_EVENTS)[number]

/** Listen to every broadcast on the `platform` channel. Returns an unsubscribe function. */
export function subscribePlatform(
  supabase: SupabaseClient,
  onEvent: (event: PlatformEvent, payload: Record<string, unknown>) => void,
): () => void {
  const channel: RealtimeChannel = supabase
    .channel('platform')
    .on('broadcast', { event: '*' }, ({ event, payload }) =>
      onEvent(event as PlatformEvent, payload as Record<string, unknown>),
    )
    .subscribe()
  return () => {
    void supabase.removeChannel(channel)
  }
}
```

Using it with the existing `supabase` client (`src/lib/supabase.ts`, which is `null` when Supabase is not configured) and React Query:

```tsx
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import { subscribePlatform } from '../lib/realtime'

export function usePlatformRefresh() {
  const queryClient = useQueryClient()
  useEffect(() => {
    if (!supabase) return
    return subscribePlatform(supabase, (event, payload) => {
      switch (event) {
        case 'batch.committed':
          queryClient.invalidateQueries({ queryKey: ['batches', payload.batch_id] })
          queryClient.invalidateQueries({ queryKey: ['seat-ledger', payload.institution_id] })
          break
        case 'review_case.created':
        case 'review_case.updated':
          queryClient.invalidateQueries({ queryKey: ['review-cases'] })
          break
        case 'admission.status_changed':
          queryClient.invalidateQueries({ queryKey: ['admissions'] })
          queryClient.invalidateQueries({ queryKey: ['seat-ledger'] })
          break
        case 'submission_window.updated':
          queryClient.invalidateQueries({ queryKey: ['submission-windows'] })
          break
        case 'edit_request.decided':
          queryClient.invalidateQueries({ queryKey: ['edit-requests'] })
          break
        case 'audit.tamper_detected':
          queryClient.invalidateQueries({ queryKey: ['audit-verify'] })
          break
      }
    })
  }, [queryClient])
}
```

The query keys are examples; use the ones your pages already use.

## Events and payloads

| Event | Payload fields | Refetch |
| --- | --- | --- |
| `batch.committed` | `batch_id`, `institution_id`, `rows_committed`, `rows_rejected`, `committed_at` | `GET /batches/{id}`, `/batches/{id}/issues`, `/institutions/{id}/seat-ledger` |
| `review_case.created` | `case_id`, `kind`, `institution_id`, `status`, `created_at` | `GET /review-cases` |
| `review_case.updated` | `case_id`, `status`, `updated_at` | `GET /review-cases/{id}` |
| `admission.status_changed` | `admission_id`, `student_id`, `from`, `to`, `changed_at` | `GET /admissions`, seat ledger (a withdrawal frees a seat) |
| `submission_window.updated` | `window_id`, `academic_year`, `state`, `updated_at` | `GET /submission-windows` |
| `edit_request.decided` | `edit_request_id`, `admission_id`, `status`, `decided_at` | the edit request list / admission |
| `audit.tamper_detected` | `first_broken_index`, `checked`, `detected_at` | `GET /audit/verify` |

Example (`batch.committed`):

```json
{
  "batch_id": "30000000-0000-4000-8000-000000000001",
  "institution_id": "10000000-0000-4000-8000-000000000003",
  "rows_committed": 71,
  "rows_rejected": 4,
  "committed_at": "2026-09-02T10:15:00Z"
}
```

Example (`admission.status_changed` for a withdrawal):

```json
{
  "admission_id": "50000000-0000-4000-8000-000000000004",
  "student_id": "40000000-0000-4000-8000-000000000004",
  "from": "submitted",
  "to": "withdrawn",
  "changed_at": "2026-09-04T12:30:00Z"
}
```

## Notes

- Broadcasts are best effort. A failed send never fails the API call, so treat events as hints to refetch, not as the source of truth. A page should also load correctly with no events at all, for example in mock mode with Supabase not configured.
- The channel is public Broadcast, readable with the anon key. Nothing sensitive is in a payload by design.
- To watch the channel from a terminal while you work: `cd backend; uv run python -m scripts.realtime_probe --seconds 60`.
