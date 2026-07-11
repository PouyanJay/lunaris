-- Course cover images (course-cover-images T0/T1): the job spine — `cover_jobs` queue table +
-- `course-covers` bucket.
--
-- Mirrors the `video_jobs` spine (20260612100000) but for the per-course AI cover: one row per
-- course (there is no kind / lesson_id / contract_hash — a course has exactly one cover). The job is
-- the Postgres-backed queue the cover worker drains (atomic claim via FOR UPDATE SKIP LOCKED lives
-- in a service-only RPC — see 20260710120100_claim_cover_job.sql) AND the status record the reader
-- polls (the cover slot renders straight off `status`). `id` is the job_id (uuid4().hex) and the
-- run-scope correlation id across queue → worker → storage → API logs.
--
-- Posture (identical to video_jobs): owner-scoped SELECT for `authenticated`; writes are
-- SERVER-ONLY (enqueue/claim/settle go through the API or worker as service_role, which bypasses
-- RLS) — so even the owner's JWT cannot spoof a claim or flip a status. Enqueue enforces the
-- OpenAI-key (keyed-tier) check app-side; a keyless account never enqueues and falls back to the
-- Typographic cover.
--
-- The `course-covers` bucket is PRIVATE (the API issues signed URLs). Objects follow
-- `{user_id}/{course_id}/{job_id}/…`, so course deletion is a prefix-delete and the storage policy
-- scopes reads to the first path segment = auth.uid().
--
-- To reverse: drop policy course_covers_select_own on storage.objects; delete from storage.buckets
-- where id = 'course-covers'; drop table if exists public.cover_jobs;

create table if not exists public.cover_jobs (
    id            text primary key,           -- job_id (uuid4().hex); the correlation id
    -- owner (RLS subject); FK + cascade so account deletion cannot leave orphaned jobs
    -- (mirrors video_jobs / provider_credentials / user_runtime_config).
    user_id       uuid not null references auth.users (id) on delete cascade,
    course_id     text not null,              -- the course this cover belongs to
    status        text not null default 'queued'
        check (status in ('queued', 'art_directing', 'rendering', 'qa',
                          'uploading', 'ready', 'failed', 'cancelled')),
    style_preset  text not null default 'nocturne',  -- art-direction preset snapshot at enqueue
    input_hash    text not null,              -- hash of the generation inputs (staleness detection)
    config        jsonb not null default '{}'::jsonb,  -- model/quality snapshot at enqueue
    attempts      integer not null default 0, -- claim count (dead-letter cap lives app-side)
    claimed_at    timestamptz,                -- lease start; a requeue sweep keys off this
    claimed_by    text,                       -- worker identity that holds the lease
    error         text,                       -- terminal failure detail (user-safe message)
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- The worker claims oldest-queued-first; a partial index keeps the claim scan cheap as the table
-- accumulates terminal rows.
create index if not exists cover_jobs_queued_idx
    on public.cover_jobs (created_at) where status = 'queued';
-- The API reads/dedups a course's cover job by (course, owner).
create index if not exists cover_jobs_course_id_idx on public.cover_jobs (course_id);
create index if not exists cover_jobs_user_id_idx on public.cover_jobs (user_id);

-- RLS (BLOCKING): owner-scoped SELECT only. Writes have no grant and no policy — server-only.
alter table public.cover_jobs enable row level security;

-- Defense in depth: strip the Supabase default grants first, then grant back exactly SELECT.
revoke all on table public.cover_jobs from public, anon, authenticated;
grant select on public.cover_jobs to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy cover_jobs_select_own on public.cover_jobs
    for select to authenticated using ((select auth.uid()) = user_id);

-- ── course-covers bucket ──────────────────────────────────────────────────────────
-- Private bucket; the worker uploads via service_role, the API issues signed URLs for display.
insert into storage.buckets (id, name, public)
values ('course-covers', 'course-covers', false)
on conflict (id) do nothing;

-- Owner-scoped read on the path convention's first segment ({user_id}/...). No write policies —
-- only service_role writes objects. storage.objects already has RLS enabled by Supabase.
create policy course_covers_select_own on storage.objects
    for select to authenticated
    using (
        bucket_id = 'course-covers'
        and (storage.foldername(name))[1] = (select auth.uid())::text
    );
