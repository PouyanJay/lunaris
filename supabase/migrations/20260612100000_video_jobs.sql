-- Explainer-video V0-T0: the job spine — `video_jobs` queue table + `course-videos` bucket.
--
-- `video_jobs` is the Postgres-backed queue the video worker drains (claim via FOR UPDATE SKIP
-- LOCKED happens in the queue layer; this migration is schema + posture only). The job row doubles
-- as the status record the UI reads, so the reader's hero slot polls job state without a second
-- store. One row per video (kind: summary | overview | lesson); `id` is the job_id (uuid4().hex)
-- and acts as the run-scope correlation id across queue → worker → storage → API logs.
--
-- Posture: owner-scoped SELECT for `authenticated` (a user may watch their own job's progress);
-- writes are SERVER-ONLY — enqueue/claim/complete go through the API or worker via service_role
-- (which bypasses RLS), because enqueue must enforce the VIDEO_GENERATION_ENABLED flag and the
-- keyed-tier check app-side. No INSERT/UPDATE/DELETE grant for authenticated, so even the owner's
-- JWT cannot spoof a claim or flip a status.
--
-- The `course-videos` bucket is PRIVATE (playback via signed URLs issued by the API). Objects
-- follow `{user_id}/{course_id}/{job_id}/…`, so course deletion is a prefix-delete (plan §8.6)
-- and the storage policy scopes reads to the first path segment = auth.uid().
--
-- To reverse: drop policy course_videos_select_own on storage.objects; delete from storage.buckets
-- where id = 'course-videos'; drop table if exists public.video_jobs;

create table if not exists public.video_jobs (
    id            text primary key,           -- job_id (uuid4().hex); the correlation id
    -- owner (RLS subject); stamped by the service path. FK + cascade so account deletion
    -- cannot leave orphaned jobs (mirrors provider_credentials / user_runtime_config).
    user_id       uuid not null references auth.users (id) on delete cascade,
    course_id     text not null,              -- the course this video belongs to
    lesson_id     text,                       -- null for course-level kinds (summary/overview)
    kind          text not null
        check (kind in ('summary', 'overview', 'lesson')),
    status        text not null default 'queued'
        check (status in ('queued', 'planning', 'coding', 'rendering', 'qa',
                          'voicing', 'assembling', 'ready', 'failed')),
    input_hash    text not null,              -- hash of the generation inputs (staleness detection)
    contract_hash text,                       -- hash of scene_contracts.json once planned (cache key)
    config        jsonb not null default '{}'::jsonb,  -- length/voice/style snapshot at enqueue
    attempts      integer not null default 0, -- claim count (dead-letter cap lives app-side)
    claimed_at    timestamptz,                -- lease start; a requeue sweep keys off this
    claimed_by    text,                       -- worker identity that holds the lease
    error         text,                       -- terminal failure detail (user-safe message)
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    -- lesson videos must point at a lesson; course-level kinds must not.
    constraint video_jobs_lesson_id_matches_kind
        check ((kind = 'lesson') = (lesson_id is not null))
);

-- The worker claims oldest-queued-first; a partial index keeps the claim scan cheap as the table
-- accumulates terminal rows.
create index if not exists video_jobs_queued_idx
    on public.video_jobs (created_at) where status = 'queued';
-- The UI lists a course's jobs; the API filters by owner.
create index if not exists video_jobs_course_id_idx on public.video_jobs (course_id);
create index if not exists video_jobs_user_id_idx on public.video_jobs (user_id);

-- RLS (BLOCKING): owner-scoped SELECT only. Writes have no grant and no policy — server-only.
alter table public.video_jobs enable row level security;

-- Defense in depth: strip the Supabase default grants first, then grant back exactly SELECT.
revoke all on table public.video_jobs from public, anon, authenticated;
grant select on public.video_jobs to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy video_jobs_select_own on public.video_jobs
    for select to authenticated using ((select auth.uid()) = user_id);

-- ── course-videos bucket ──────────────────────────────────────────────────────────
-- Private bucket; the worker uploads via service_role, the API issues signed URLs for playback.
insert into storage.buckets (id, name, public)
values ('course-videos', 'course-videos', false)
on conflict (id) do nothing;

-- Owner-scoped read on the path convention's first segment ({user_id}/...). No write policies —
-- only service_role writes objects. storage.objects already has RLS enabled by Supabase.
create policy course_videos_select_own on storage.objects
    for select to authenticated
    using (
        bucket_id = 'course-videos'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );
