-- Unified UI Phase 9: learning telemetry — the activity feed's events + coarse study minutes.
--
-- Two owner-scoped tables (the learner_progress posture): the progress endpoints append immutable
-- learning_events rows (lesson started/completed, concept mastered) and the reader's session
-- heartbeat upserts study_minutes buckets. The Activity screen's streaks/heat/feed and the Home
-- greeting's streak all derive from these rows in the API — no stored rollups, no triggers.
--
-- Identity notes:
--  * learning_events is APPEND-ONLY telemetry: rows are historical facts, so course/lesson titles
--    are denormalized at write time (the feed must survive a course rebuild or deletion) and
--    course_id carries no hard FK to public.courses (the video_jobs / learner_progress precedent).
--  * event_type is kept in lockstep with the API's LearningEventType literal; 'verified' is
--    reserved (nothing emits it yet).
--  * study_minutes rows are minute-aligned buckets, one per studied minute — deliberately coarse
--    (privacy: no content refs, just "was studying"), enforced by the bucket_start check.
--
-- Access posture: RLS enabled with owner-only policies for `authenticated`; the backend
-- service_role client (bypasses RLS) reads/writes on the caller's behalf with app-layer scoping.
-- learning_events deviates from the four-policy house pattern on purpose: telemetry is
-- append-only, so `authenticated` gets no UPDATE or DELETE policy/grant (history can't be
-- rewritten from a user JWT; account deletion cascades via auth.users).
--
-- To reverse: DROP TABLE IF EXISTS public.learning_events, public.study_minutes;

create table if not exists public.learning_events (
    id           bigint generated always as identity primary key,
    user_id      uuid not null references auth.users (id) on delete cascade,
    event_type   text not null check (event_type in ('started', 'completed', 'mastered', 'verified')),
    course_id    text not null check (length(course_id) between 1 and 100),
    course_title text check (length(course_title) between 1 and 300),
    lesson_id    text check (length(lesson_id) between 1 and 200),
    lesson_title text check (length(lesson_title) between 1 and 300),
    kc_id        text check (length(kc_id) between 1 and 200),
    kc_label     text check (length(kc_label) between 1 and 300),
    occurred_at  timestamptz not null default now()
);

-- The one read shape: a user's history newest-first (feed + streak derivation).
create index if not exists learning_events_user_occurred_idx
    on public.learning_events (user_id, occurred_at desc);

create table if not exists public.study_minutes (
    user_id      uuid not null references auth.users (id) on delete cascade,
    bucket_start timestamptz not null check (date_trunc('minute', bucket_start) = bucket_start),
    -- One row per studied minute; the API upserts on this PK so heartbeats are idempotent.
    primary key (user_id, bucket_start)
);

-- RLS (BLOCKING): owner-scoped on both tables — the learner reads and writes their own telemetry.
alter table public.learning_events enable row level security;
alter table public.study_minutes enable row level security;

-- Defense in depth: drop the default anon/public grants entirely; authenticated keeps a grant
-- matched to each table's posture and RLS constrains it to its own rows. learning_events also
-- revokes authenticated's DEFAULT all-privileges grant so the append-only posture holds at the
-- grant layer, not just via absent policies.
revoke all on table public.learning_events from public, anon, authenticated;
revoke all on table public.study_minutes from public, anon, authenticated;

-- Append-only: no update/delete grant on events (see header). The identity sequence needs no
-- grant — GENERATED ALWAYS columns are filled server-side on insert.
grant select, insert on public.learning_events to authenticated;
-- Minute buckets are upserted (insert ... on conflict do update), so update stays granted.
grant select, insert, update, delete on public.study_minutes to authenticated;

-- Backfill (security-review finding): the Phase-2 progress tables only revoked public/anon, so
-- `authenticated` kept Postgres's default TRUNCATE/REFERENCES/TRIGGER — and TRUNCATE is not
-- governed by RLS at all (a cross-tenant wipe vector). Re-narrow them to the intended CRUD set.
revoke truncate, references, trigger on table public.objective_progress from authenticated;
revoke truncate, references, trigger on table public.lesson_progress from authenticated;
revoke truncate, references, trigger on table public.learner_course_state from authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy learning_events_select_own on public.learning_events
    for select to authenticated using ((select auth.uid()) = user_id);
create policy learning_events_insert_own on public.learning_events
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);

create policy study_minutes_select_own on public.study_minutes
    for select to authenticated using ((select auth.uid()) = user_id);
create policy study_minutes_insert_own on public.study_minutes
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy study_minutes_update_own on public.study_minutes
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy study_minutes_delete_own on public.study_minutes
    for delete to authenticated using ((select auth.uid()) = user_id);
