<!-- Owner: Dev B -->
# supabase

Postgres schema and seed for the APAAR Integrity Platform.

| File | Purpose |
| --- | --- |
| `migrations/20261022154039_init_schema.sql` | Enums, tables, indexes, RLS enabled on every table (no policies yet), Realtime publication for `review_cases`, `admissions`, `batches` |
| `migrations/20261023130407_pipeline.sql` | Upload staging (`batch_rows`), batch counts, active admissions, contact and exam columns |
| `migrations/20261023135641_windows_corrections.sql` | `submission_windows`, correction batches (`parent_batch_id`), withdrawal and student-response columns, review-case notes, institution webhook and demo-loader `origin` columns |
| `seed.sql` | The 3 synthetic institutions from the backend mock fixtures, their programmes and `2026-27` seat pools (same ids) |

Schema changes go in **new** files in `migrations/`. Never edit a migration after it has been pushed.

## Setup (Sam runs these; AI tools never do)

From the repo root:

```sh
npx supabase init                              # only if supabase/config.toml does not exist; keep the existing migrations/
npx supabase login
npx supabase link --project-ref <ref>          # <ref> is in the dashboard URL
npx supabase db push                           # applies migrations/ to the linked project
```

Load the seed:

1. Open the Supabase dashboard → **SQL Editor** → **New query**.
2. Paste the contents of `supabase/seed.sql` and click **Run**.
3. Check **Table Editor**: `institutions` has 3 rows, `programmes` 6, `seat_pools` 24.

The backend uses the service role key, which bypasses RLS. Per-role RLS policies are Dev B's next task.
