-- Phase 2 (multi-tenancy): per-user ownership + RLS policies on the user-owned tables.
--
-- Adds `user_id uuid` to courses, course_runs, and run_events and gives `authenticated` owner-only
-- RLS policies, so a Supabase client bound to a user's JWT can read/write ONLY that user's rows —
-- the DB enforces isolation, not just app code. The backend's service_role client keeps full access
-- (service_role bypasses RLS), so the build path (which runs as a background task that can outlive a
-- user's short-lived JWT) still writes via service_role, stamping the owner's user_id explicitly.
--
-- Additive + safe to deploy ahead of the app layer: `user_id` is nullable, so existing rows become
-- orphaned (null owner — invisible to authenticated, still reachable by service_role) and nothing
-- breaks. Existing dev/prod rows are throwaway (no real users yet), so no backfill.
--
-- The shared grounding corpus (grounding_documents, source_authorities) is intentionally NOT touched
-- here — it is a global, service_role-owned asset shared across users, not per-user data.
--
-- To reverse: drop the policies, the grants, and the user_id columns (see bottom).

-- ── courses ────────────────────────────────────────────────────────────────────────────────────
alter table public.courses add column if not exists user_id uuid;
create index if not exists courses_user_id_idx on public.courses (user_id);

-- RLS policies require the role to hold table privileges; the create migration revoked them from
-- authenticated, so grant them back here — RLS then constrains authenticated to its own rows.
grant select, insert, update, delete on public.courses to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy courses_select_own on public.courses
    for select to authenticated using ((select auth.uid()) = user_id);
create policy courses_insert_own on public.courses
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy courses_update_own on public.courses
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy courses_delete_own on public.courses
    for delete to authenticated using ((select auth.uid()) = user_id);

-- ── course_runs ────────────────────────────────────────────────────────────────────────────────
alter table public.course_runs add column if not exists user_id uuid;
create index if not exists course_runs_user_id_idx on public.course_runs (user_id);
grant select, insert, update, delete on public.course_runs to authenticated;

create policy course_runs_select_own on public.course_runs
    for select to authenticated using ((select auth.uid()) = user_id);
create policy course_runs_insert_own on public.course_runs
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy course_runs_update_own on public.course_runs
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy course_runs_delete_own on public.course_runs
    for delete to authenticated using ((select auth.uid()) = user_id);

-- ── run_events ─────────────────────────────────────────────────────────────────────────────────
alter table public.run_events add column if not exists user_id uuid;
create index if not exists run_events_user_id_idx on public.run_events (user_id);
grant select, insert, update, delete on public.run_events to authenticated;

create policy run_events_select_own on public.run_events
    for select to authenticated using ((select auth.uid()) = user_id);
create policy run_events_insert_own on public.run_events
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy run_events_update_own on public.run_events
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy run_events_delete_own on public.run_events
    for delete to authenticated using ((select auth.uid()) = user_id);

-- Reverse:
--   drop policy if exists courses_select_own on public.courses;  (… and the other 11 policies)
--   revoke select, insert, update, delete on public.courses, public.course_runs, public.run_events
--     from authenticated;
--   alter table public.courses drop column if exists user_id;  (… course_runs, run_events)
