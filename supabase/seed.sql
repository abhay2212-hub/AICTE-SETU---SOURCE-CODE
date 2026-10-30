-- Owner: Dev B
-- Synthetic seed data. Matches backend/app/mocks: same ids, institutions, programmes
-- and 2026-27 seat pools. Load through the Supabase SQL editor after the migration.

begin;

insert into public.institutions (id, aicte_code, name, state, parent_trust) values
  ('10000000-0000-4000-8000-000000000001', '1-9999001', 'Meghdoot Institute of Engineering', 'Maharashtra', 'Meghdoot Shikshan Sanstha'),
  ('10000000-0000-4000-8000-000000000002', '1-9999002', 'Narmada Valley College of Technology', 'Madhya Pradesh', 'Narmada Vidya Trust'),
  ('10000000-0000-4000-8000-000000000003', '1-9999003', 'Shadow Institute of Technology', 'Uttar Pradesh', 'Shadow Educational Trust')
on conflict (id) do nothing;

insert into public.programmes (id, institution_id, code, name, level, duration_years) values
  ('20000000-0000-4000-8000-000000000011', '10000000-0000-4000-8000-000000000001', 'UG-CSE', 'B.Tech Computer Science and Engineering', 'UG', 4),
  ('20000000-0000-4000-8000-000000000012', '10000000-0000-4000-8000-000000000001', 'UG-ME', 'B.Tech Mechanical Engineering', 'UG', 4),
  ('20000000-0000-4000-8000-000000000021', '10000000-0000-4000-8000-000000000002', 'UG-CSE', 'B.Tech Computer Science and Engineering', 'UG', 4),
  ('20000000-0000-4000-8000-000000000022', '10000000-0000-4000-8000-000000000002', 'UG-ECE', 'B.Tech Electronics and Communication Engineering', 'UG', 4),
  ('20000000-0000-4000-8000-000000000031', '10000000-0000-4000-8000-000000000003', 'UG-CSE', 'B.Tech Computer Science and Engineering', 'UG', 4),
  ('20000000-0000-4000-8000-000000000032', '10000000-0000-4000-8000-000000000003', 'UG-CE', 'B.Tech Civil Engineering', 'UG', 4)
on conflict (id) do nothing;

insert into public.seat_pools (programme_id, academic_year, pool, approved_seats, rule_version) values
  ('20000000-0000-4000-8000-000000000011', '2026-27', 'regular', 102, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000011', '2026-27', 'tfw', 6, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000011', '2026-27', 'fn_oci_pio', 6, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000011', '2026-27', 'nri', 6, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000012', '2026-27', 'regular', 51, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000012', '2026-27', 'tfw', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000012', '2026-27', 'fn_oci_pio', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000012', '2026-27', 'nri', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000021', '2026-27', 'regular', 102, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000021', '2026-27', 'tfw', 6, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000021', '2026-27', 'fn_oci_pio', 6, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000021', '2026-27', 'nri', 6, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000022', '2026-27', 'regular', 51, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000022', '2026-27', 'tfw', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000022', '2026-27', 'fn_oci_pio', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000022', '2026-27', 'nri', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000031', '2026-27', 'regular', 51, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000031', '2026-27', 'tfw', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000031', '2026-27', 'fn_oci_pio', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000031', '2026-27', 'nri', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000032', '2026-27', 'regular', 51, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000032', '2026-27', 'tfw', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000032', '2026-27', 'fn_oci_pio', 3, 'APH-2026-27-v1'),
  ('20000000-0000-4000-8000-000000000032', '2026-27', 'nri', 3, 'APH-2026-27-v1')
on conflict (programme_id, academic_year, pool, rule_version) do nothing;

commit;
