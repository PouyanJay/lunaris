-- Unified UI Phase 2: the per-learner progress substrate — objective mastery + lesson state.
--
-- Two owner-scoped tables (the user_runtime_config posture): the learner marks a module objective
-- "understood" and moves lessons through in_progress → done; Home/Overview/Map/Activity all derive
-- from these rows. Aggregates (course %, kc mastery) are computed in the API from the course
-- payload + these rows — no stored rollups, no triggers.
--
-- Identity notes:
--  * Objectives carry no id in the course schema, so a row is keyed by
--    (user_id, course_id, module_id, objective_index) — the index is the objective's position in
--    the module's objectives array. Row present = understood; un-marking deletes the row.
--  * lesson_id is the stable "{module_id}-l0" id the authoring pipeline emits.
--  * course_id is text without a hard FK to public.courses (the video_jobs precedent): progress
--    outlives course rebuilds that replace the payload, and deletion cleanup is app-level.
--
-- Access posture: RLS enabled with owner-only policies for `authenticated`; the backend
-- service_role client (bypasses RLS) reads/writes on the caller's behalf with app-layer scoping.
--
-- To reverse: DROP TABLE IF EXISTS public.objective_progress, public.lesson_progress;

create table if not exists public.objective_progress (
    user_id         uuid not null references auth.users (id) on delete cascade,
    course_id       text not null check (length(course_id) between 1 and 100),
    module_id       text not null check (length(module_id) between 1 and 200),
    -- Position in the module's objectives array (modules carry a handful of objectives).
    objective_index integer not null check (objective_index between 0 and 999),
    understood_at   timestamptz not null default now(),
    -- Row present = understood: the API upserts on this PK and deletes to un-mark.
    primary key (user_id, course_id, module_id, objective_index)
);

create table if not exists public.lesson_progress (
    user_id    uuid not null references auth.users (id) on delete cascade,
    course_id  text not null check (length(course_id) between 1 and 100),
    lesson_id  text not null check (length(lesson_id) between 1 and 200),
    -- The lesson's learner state; kept in lockstep with the API's LessonState literal.
    state      text not null check (state in ('in_progress', 'done')),
    updated_at timestamptz not null default now(),
    -- One state per lesson per user; the API upserts on this PK to advance it.
    primary key (user_id, course_id, lesson_id)
);

-- RLS (BLOCKING): owner-scoped on both tables — the learner reads and writes their own progress.
alter table public.objective_progress enable row level security;
alter table public.lesson_progress enable row level security;

-- Defense in depth: drop the default anon/public grants entirely; authenticated keeps its grant
-- and RLS constrains it to its own rows.
revoke all on table public.objective_progress from public, anon;
revoke all on table public.lesson_progress from public, anon;

grant select, insert, update, delete on public.objective_progress to authenticated;
grant select, insert, update, delete on public.lesson_progress to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy objective_progress_select_own on public.objective_progress
    for select to authenticated using ((select auth.uid()) = user_id);
create policy objective_progress_insert_own on public.objective_progress
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy objective_progress_update_own on public.objective_progress
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy objective_progress_delete_own on public.objective_progress
    for delete to authenticated using ((select auth.uid()) = user_id);

create policy lesson_progress_select_own on public.lesson_progress
    for select to authenticated using ((select auth.uid()) = user_id);
create policy lesson_progress_insert_own on public.lesson_progress
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy lesson_progress_update_own on public.lesson_progress
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy lesson_progress_delete_own on public.lesson_progress
    for delete to authenticated using ((select auth.uid()) = user_id);
