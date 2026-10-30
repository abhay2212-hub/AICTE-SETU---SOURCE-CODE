-- Owner: Dev B
-- Data pipeline: upload staging, batch counts, active admissions and the columns the
-- ingestion pipeline stores. Safe to run once on a database with the init migration applied.

-- ---------------------------------------------------------------------------
-- Upload staging: one row per data row of an uploaded file.
-- raw holds the uploaded cells keyed by original header, with contact-like values already
-- replaced by HMAC hashes; normalized holds the mapped, normalised row (no raw contacts).
-- ---------------------------------------------------------------------------
create table if not exists public.batch_rows (
  id bigint generated always as identity primary key,
  batch_id uuid not null references public.batches (id) on delete cascade,
  row_number integer not null,
  raw jsonb not null,
  normalized jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'valid', 'error', 'committed', 'skipped')),
  unique (batch_id, row_number)
);

-- ---------------------------------------------------------------------------
-- Batches: counts as one json object, plus the committed result for idempotent commits.
-- ---------------------------------------------------------------------------
alter table public.batches add column if not exists column_mapping jsonb;
alter table public.batches add column if not exists counts jsonb not null default '{}'::jsonb;
alter table public.batches add column if not exists header jsonb;
alter table public.batches add column if not exists commit_result jsonb;

-- ---------------------------------------------------------------------------
-- Admissions: active flag (withdrawn or superseded rows become inactive) and exam name.
-- ---------------------------------------------------------------------------
alter table public.admissions add column if not exists active boolean not null default true;
alter table public.admissions add column if not exists qualifying_exam text;

-- At most one active admission per student, programme and academic year.
create unique index if not exists admissions_one_active_idx
  on public.admissions (student_id, programme_id, academic_year)
  where active;

-- ---------------------------------------------------------------------------
-- Students: the email hash next to the phone hash in contact_hash, plus fields Blind Match
-- will encode later. Hashes are HMAC-SHA256; raw contacts are never stored.
-- ---------------------------------------------------------------------------
alter table public.students add column if not exists email_hash text;
alter table public.students add column if not exists guardian_name text;
alter table public.students add column if not exists domicile_state text;

-- ---------------------------------------------------------------------------
-- Validation issues: the human-readable message shown in the issues list.
-- ---------------------------------------------------------------------------
alter table public.validation_issues add column if not exists message text;

-- ---------------------------------------------------------------------------
-- Indexes used by the pipeline
-- ---------------------------------------------------------------------------
create index if not exists batch_rows_batch_idx on public.batch_rows (batch_id);
create index if not exists validation_issues_batch_idx on public.validation_issues (batch_id);
create index if not exists admissions_batch_idx on public.admissions (batch_id);
create index if not exists admissions_student_active_idx on public.admissions (student_id) where active;
create index if not exists review_cases_institution_idx on public.review_cases (institution_id);
create index if not exists students_contact_hash_idx on public.students (contact_hash);

-- ---------------------------------------------------------------------------
-- Row level security: same as the init migration, enabled with no policies.
-- ---------------------------------------------------------------------------
alter table public.batch_rows enable row level security;
