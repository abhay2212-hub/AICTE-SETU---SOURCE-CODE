-- Owner: Dev B
-- Submission windows and the post-lock edit flow, withdrawals, corrections, student
-- responses, institution webhooks and demo-loader markers. Idempotent: safe to run again.

-- ---------------------------------------------------------------------------
-- Submission windows, set by AICTE. Uploads and commits for an academic year are allowed
-- only between opens_at and closes_at and while locked_at is null. After that, changes to
-- an admission go through an edit request an aicte_admin decides.
-- ---------------------------------------------------------------------------
create table if not exists public.submission_windows (
  id uuid primary key default gen_random_uuid(),
  academic_year text not null unique check (academic_year ~ '^\d{4}-\d{2}$'),
  opens_at timestamptz not null,
  closes_at timestamptz not null,
  locked_at timestamptz,
  locked_by uuid references auth.users (id),
  created_by uuid references auth.users (id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint submission_windows_order check (closes_at > opens_at)
);

-- ---------------------------------------------------------------------------
-- Institutions: rows created by backend/scripts/load_demo.py carry origin = 'load_demo' so
-- a later --reset can remove them. Seed rows keep origin null.
-- Outbound webhook: batch.committed is POSTed to webhook_url, signed with a secret derived
-- server-side from webhook_key_id; the secret itself is never stored.
-- ---------------------------------------------------------------------------
alter table public.institutions add column if not exists origin text;
alter table public.institutions add column if not exists webhook_url text;
alter table public.institutions add column if not exists webhook_key_id text;

-- ---------------------------------------------------------------------------
-- Batches: a correction batch points at the batch whose rejected rows it fixes.
-- ---------------------------------------------------------------------------
alter table public.batches add column if not exists parent_batch_id uuid
  references public.batches (id) on delete cascade;

-- ---------------------------------------------------------------------------
-- Admissions: withdrawal and student-response bookkeeping.
-- ---------------------------------------------------------------------------
alter table public.admissions add column if not exists withdrawn_at timestamptz;
alter table public.admissions add column if not exists withdrawal_reason text;
alter table public.admissions add column if not exists responded_at timestamptz;
alter table public.admissions add column if not exists response_channel text;

-- ---------------------------------------------------------------------------
-- Review cases: dated notes added by the system (e.g. a withdrawal that brings an
-- overrun pool back within capacity). Each note is {"at": iso8601, "text": "..."}.
-- ---------------------------------------------------------------------------
alter table public.review_cases add column if not exists notes jsonb not null default '[]'::jsonb;

-- At most one open dispute case per admission, so repeated disputes stay idempotent.
create unique index if not exists review_cases_open_dispute_idx
  on public.review_cases ((evidence->>'admission_id'))
  where kind = 'dispute' and status = 'open';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index if not exists batches_parent_idx on public.batches (parent_batch_id);
create index if not exists admissions_status_created_idx
  on public.admissions (status, created_at) where active;
create index if not exists api_keys_institution_idx on public.api_keys (institution_id);

-- ---------------------------------------------------------------------------
-- Row level security: enabled with no policies, like every other table.
-- ---------------------------------------------------------------------------
alter table public.submission_windows enable row level security;
