-- Owner: Dev B
-- Initial schema for the APAAR Integrity Platform. Synthetic data only; never store Aadhaar.
-- Schema changes go in new migration files; do not edit this one after it is pushed.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type public.app_role as enum (
  'institution_admin', 'institution_operator', 'aicte_admin', 'student', 'verifier', 'auditor'
);
create type public.seat_pool as enum ('regular', 'tfw', 'fn_oci_pio', 'nri');
create type public.admission_status as enum (
  'submitted', 'student_confirmed', 'student_disputed', 'no_response', 'withdrawn'
);
create type public.batch_status as enum ('uploaded', 'mapped', 'validated', 'committed', 'failed');
create type public.issue_severity as enum ('error', 'warning', 'review', 'info');
create type public.case_status as enum ('open', 'confirmed', 'dismissed', 'correction_requested');

-- ---------------------------------------------------------------------------
-- Institutions, programmes and the Seat Ledger
-- ---------------------------------------------------------------------------
create table public.institutions (
  id uuid primary key default gen_random_uuid(),
  aicte_code text not null unique,
  name text not null,
  state text not null,
  parent_trust text,
  created_at timestamptz not null default now()
);

create table public.programmes (
  id uuid primary key default gen_random_uuid(),
  institution_id uuid not null references public.institutions (id) on delete cascade,
  code text not null,
  name text not null,
  level text not null default 'UG',
  duration_years smallint not null default 4 check (duration_years > 0),
  created_at timestamptz not null default now(),
  unique (institution_id, code)
);

create table public.seat_pools (
  id uuid primary key default gen_random_uuid(),
  programme_id uuid not null references public.programmes (id) on delete cascade,
  academic_year text not null check (academic_year ~ '^\d{4}-\d{2}$'),
  pool public.seat_pool not null,
  approved_seats integer not null check (approved_seats >= 0),
  rule_version text not null,
  created_at timestamptz not null default now(),
  unique (programme_id, academic_year, pool, rule_version)
);

-- ---------------------------------------------------------------------------
-- People
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  role public.app_role not null,
  institution_id uuid references public.institutions (id),
  display_name text,
  created_at timestamptz not null default now()
);

create table public.students (
  id uuid primary key default gen_random_uuid(),
  apaar_id text unique check (apaar_id is null or apaar_id ~ '^\d{12}$'),
  provisional_id text unique,
  full_name text not null,
  dob date not null,
  gender text not null,
  category text not null,
  pwd boolean not null default false,
  nationality text not null default 'IN',
  oci_status boolean not null default false,
  fn_status boolean not null default false,
  contact_hash text,
  opted_out boolean not null default false,
  bloom_identity bytea,
  created_at timestamptz not null default now(),
  constraint students_identifier_present check (apaar_id is not null or provisional_id is not null)
);

-- ---------------------------------------------------------------------------
-- Uploads, admissions and validation
-- ---------------------------------------------------------------------------
create table public.batches (
  id uuid primary key default gen_random_uuid(),
  institution_id uuid not null references public.institutions (id),
  uploaded_by uuid references auth.users (id),
  file_name text not null,
  file_hash text not null,
  status public.batch_status not null default 'uploaded',
  column_mapping jsonb,
  rows_total integer not null default 0,
  rows_error integer not null default 0,
  rows_warning integer not null default 0,
  rows_review integer not null default 0,
  rows_info integer not null default 0,
  created_at timestamptz not null default now(),
  committed_at timestamptz,
  unique (institution_id, file_hash)
);

create table public.admissions (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students (id),
  programme_id uuid not null references public.programmes (id),
  academic_year text not null check (academic_year ~ '^\d{4}-\d{2}$'),
  pool public.seat_pool not null,
  admission_mode text not null check (admission_mode in ('cap', 'management', 'lateral', 'spot')),
  admission_date date not null,
  qualifying_exam_pct numeric(5, 2) check (qualifying_exam_pct between 0 and 100),
  status public.admission_status not null default 'submitted',
  batch_id uuid references public.batches (id),
  created_at timestamptz not null default now()
);

create table public.validation_issues (
  id bigint generated always as identity primary key,
  batch_id uuid not null references public.batches (id) on delete cascade,
  row_number integer not null,
  rule_code text not null,
  severity public.issue_severity not null,
  details jsonb not null default '{}'::jsonb,
  resolved boolean not null default false,
  resolved_by uuid references auth.users (id),
  resolved_at timestamptz,
  resolution_note text
);

-- ---------------------------------------------------------------------------
-- Review and corrections
-- ---------------------------------------------------------------------------
create table public.review_cases (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('intake_overrun', 'blind_match', 'dispute', 'signal')),
  institution_id uuid not null references public.institutions (id),
  title text not null,
  evidence jsonb not null default '{}'::jsonb,
  status public.case_status not null default 'open',
  reviewer_id uuid references auth.users (id),
  reviewer_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table public.edit_requests (
  id uuid primary key default gen_random_uuid(),
  admission_id uuid not null references public.admissions (id) on delete cascade,
  field text not null,
  old_value text,
  new_value text not null,
  reason text not null,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  requested_by uuid references auth.users (id),
  decided_by uuid references auth.users (id),
  decision_note text,
  created_at timestamptz not null default now(),
  decided_at timestamptz
);

-- ---------------------------------------------------------------------------
-- Student side: consent, access log, credentials, Telegram
-- ---------------------------------------------------------------------------
create table public.consents (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students (id) on delete cascade,
  verifier_id text not null,
  verifier_name text not null,
  purpose text not null,
  fields text[] not null,
  granted_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create table public.access_log (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students (id) on delete cascade,
  accessor text not null,
  accessor_role public.app_role not null,
  purpose text not null,
  fields text[] not null,
  consent_id uuid references public.consents (id),
  accessed_at timestamptz not null default now()
);

create table public.credential_revocations (
  credential_id uuid primary key,
  student_id uuid references public.students (id),
  reason text not null,
  revoked_at timestamptz not null default now()
);

create table public.telegram_links (
  id uuid primary key default gen_random_uuid(),
  student_id uuid not null references public.students (id) on delete cascade,
  chat_id bigint unique,
  link_token text not null unique,
  linked_at timestamptz,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Integration API keys and audit log
-- ---------------------------------------------------------------------------
create table public.api_keys (
  id uuid primary key default gen_random_uuid(),
  institution_id uuid not null references public.institutions (id) on delete cascade,
  key_hash text not null unique,
  created_at timestamptz not null default now(),
  revoked_at timestamptz
);

create table public.audit_events (
  id bigserial primary key,
  actor text not null,
  action text not null,
  entity_type text not null,
  entity_id text,
  payload jsonb not null default '{}'::jsonb,
  prev_hash text not null,
  hash text not null unique,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index admissions_programme_year_idx on public.admissions (programme_id, academic_year);
create index students_apaar_id_idx on public.students (apaar_id);
create index review_cases_status_idx on public.review_cases (status);

-- ---------------------------------------------------------------------------
-- Row level security
-- The backend connects with the service role, which bypasses RLS. Every table has RLS
-- enabled and no policies, so anon and authenticated clients see nothing yet.
-- Writing per-role policies is Dev B's next task.
-- ---------------------------------------------------------------------------
do $$
declare
  t record;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t.tablename);
  end loop;
end;
$$;

-- ---------------------------------------------------------------------------
-- Realtime
-- ---------------------------------------------------------------------------
alter publication supabase_realtime add table public.review_cases, public.admissions, public.batches;
