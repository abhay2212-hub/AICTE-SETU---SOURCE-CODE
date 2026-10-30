-- Owner: Dev B
-- edit_requests.requested_by and decided_by record the same actor string as the audit event:
-- the user id with real login, "demo-<role>" in demo mode. Demo actors are not auth.users rows,
-- so both columns become text without the foreign key. Existing uuids are kept as their text form.
-- Idempotent: safe to run again (the type change only runs while a column is still uuid).

alter table public.edit_requests drop constraint if exists edit_requests_requested_by_fkey;
alter table public.edit_requests drop constraint if exists edit_requests_decided_by_fkey;

do $$
declare
  actor_column text;
begin
  foreach actor_column in array array['requested_by', 'decided_by'] loop
    if exists (
      select 1
      from information_schema.columns
      where table_schema = 'public'
        and table_name = 'edit_requests'
        and column_name = actor_column
        and data_type = 'uuid'
    ) then
      execute format(
        'alter table public.edit_requests alter column %1$I type text using %1$I::text',
        actor_column
      );
    end if;
  end loop;
end
$$;
