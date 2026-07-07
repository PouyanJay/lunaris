-- Unified UI Phase 3: per-learner course state — when a course was last opened, and at which
-- lesson. The My-courses library sorts by last_opened_at; the Overview/Home Continue CTA resumes
-- at last_lesson_id. One row per (user, course), touched on every course/lesson open.
--
-- Identity notes (the learner_progress posture, 20260707080000):
--  * course_id is text without a hard FK to public.courses (the video_jobs precedent): state
--    outlives course rebuilds that replace the payload; deletion cleanup is app-level.
--  * last_lesson_id is nullable — opening the Overview/Map counts as opening the course without
--    a lesson, and a bare touch must not erase a previously recorded reading position (the API
--    omits the column from the upsert payload when absent, so conflict-updates preserve it).
--
-- Access posture: RLS enabled with owner-only policies for `authenticated`; the backend
-- service_role client (bypasses RLS) reads/writes on the caller's behalf with app-layer scoping.
--
-- To reverse: DROP TABLE IF EXISTS public.learner_course_state;

create table if not exists public.learner_course_state (
    user_id        uuid not null references auth.users (id) on delete cascade,
    course_id      text not null check (length(course_id) between 1 and 100),
    last_opened_at timestamptz not null default now(),
    last_lesson_id text check (last_lesson_id is null or length(last_lesson_id) between 1 and 200),
    -- One state row per course per user; the API upserts on this PK to touch it.
    primary key (user_id, course_id)
);

-- RLS (BLOCKING): owner-scoped — the learner reads and writes their own course state.
alter table public.learner_course_state enable row level security;

-- Defense in depth: drop the default anon/public grants entirely; authenticated keeps its grant
-- and RLS constrains it to its own rows.
revoke all on table public.learner_course_state from public, anon;

grant select, insert, update, delete on public.learner_course_state to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy learner_course_state_select_own on public.learner_course_state
    for select to authenticated using ((select auth.uid()) = user_id);
create policy learner_course_state_insert_own on public.learner_course_state
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy learner_course_state_update_own on public.learner_course_state
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy learner_course_state_delete_own on public.learner_course_state
    for delete to authenticated using ((select auth.uid()) = user_id);
