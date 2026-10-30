-- Owner: Dev B
-- Cross-institution Blind Match, the student side (demo student, issued credentials) and
-- the integrity results table. Idempotent: safe to run again.

-- ---------------------------------------------------------------------------
-- Students: Blind Match block and the designated demo student.
-- bloom_identity (bytea, from the init migration) holds the 1024-bit encoding from
-- engine.blind_match.encoder.encode_identity. bloom_block is the hex HMAC-SHA256 of
-- "dob:" + ISO date of birth, keyed with BLIND_MATCH_SECRET: only students with the same
-- block are compared.
-- is_demo marks the student that role=student resolves to while MOCK_MODE=true.
-- ---------------------------------------------------------------------------
alter table public.students add column if not exists bloom_block text;
alter table public.students add column if not exists is_demo boolean not null default false;

create index if not exists students_bloom_block_idx
  on public.students (bloom_block) where bloom_block is not null;
create index if not exists students_is_demo_idx on public.students (is_demo) where is_demo;

-- ---------------------------------------------------------------------------
-- Review cases: one blind_match case per unordered student pair. evidence->>'pair_key' is
-- least(student_a, student_b) || ':' || greatest(student_a, student_b).
-- ---------------------------------------------------------------------------
create unique index if not exists review_cases_blind_match_pair_idx
  on public.review_cases ((evidence->>'pair_key'))
  where kind = 'blind_match';

-- ---------------------------------------------------------------------------
-- Issued credentials (shared/credentials.md). Holds what was signed, never the APAAR ID,
-- so revocation can check the owner and verification can log access for the student.
-- ---------------------------------------------------------------------------
create table if not exists public.credentials (
  id uuid primary key,
  student_id uuid not null references public.students (id) on delete cascade,
  admission_id uuid references public.admissions (id) on delete set null,
  audience text not null,
  pseudonym text not null,
  claims jsonb not null,
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists credentials_student_idx on public.credentials (student_id);
create index if not exists access_log_student_idx
  on public.access_log (student_id, accessed_at desc);
create index if not exists consents_student_idx on public.consents (student_id);

-- ---------------------------------------------------------------------------
-- Integrity results written by Dev A's compute job (shared/integrity-results.md).
-- ---------------------------------------------------------------------------
create table if not exists public.integrity_scores (
  id bigint generated always as identity primary key,
  institution_id uuid not null references public.institutions (id) on delete cascade,
  academic_year text not null check (academic_year ~ '^\d{4}-\d{2}$'),
  score numeric not null,
  tier text not null,
  components jsonb not null default '{}'::jsonb,
  top_features jsonb not null default '[]'::jsonb,
  signals jsonb not null default '[]'::jsonb,
  model_version text not null,
  computed_at timestamptz not null default now(),
  unique (institution_id, academic_year, model_version)
);

create index if not exists integrity_scores_latest_idx
  on public.integrity_scores (institution_id, academic_year, computed_at desc);

-- ---------------------------------------------------------------------------
-- Row level security: enabled with no policies, like every other table.
-- ---------------------------------------------------------------------------
alter table public.credentials enable row level security;
alter table public.integrity_scores enable row level security;
