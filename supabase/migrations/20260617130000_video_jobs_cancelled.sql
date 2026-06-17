-- Per-video STOP: a terminal `cancelled` status for video_jobs.
--
-- The owner can stop a video before it finishes (an automatic build job or a regenerate). A queued
-- job that is cancelled is never claimed (claim_video_job takes only 'queued' rows); an in-flight
-- job that is cancelled is aborted by the worker's cancel-watcher, which kills the render subprocess
-- — so no compute is spent on a stopped video. `cancelled` is terminal, like 'ready'/'failed'.
--
-- Two changes, both additive + deploy-safe (no existing row can hold 'cancelled', so widening the
-- CHECK rejects nothing already stored):
--   1. widen the status CHECK to allow 'cancelled';
--   2. replace requeue_stale_video_jobs so its in-flight predicate also excludes 'cancelled' — a
--      cancelled-but-still-leased job must never be requeued back to life by the lease sweep.
--
-- claim_video_job is unchanged (it already selects only status='queued'). RLS is unchanged (the
-- owner-scoped SELECT policy constrains WHICH rows, not the status value). No new table.
--
-- To reverse: cancel any in-flight stop in the app first, then narrow the CHECK back to
-- ('queued','planning','coding','rendering','qa','voicing','assembling','ready','failed') and
-- restore the prior requeue_stale_video_jobs body (drop 'cancelled' from its NOT IN lists).

alter table public.video_jobs
    drop constraint if exists video_jobs_status_check;

alter table public.video_jobs
    add constraint video_jobs_status_check
    check (status in ('queued', 'planning', 'coding', 'rendering', 'qa',
                      'voicing', 'assembling', 'ready', 'failed', 'cancelled'));

-- Replace the lease sweep so 'cancelled' counts as terminal: a cancelled in-flight job (the owner
-- stopped it while a worker still held the lease) must be skipped, never requeued or dead-lettered.
-- Otherwise unchanged from 20260614130000 — same SECURITY INVOKER / VOLATILE / pinned search_path,
-- dead-letter-before-requeue ordering, and idempotence.
create or replace function public.requeue_stale_video_jobs(p_lease_seconds int, p_max_attempts int)
returns table (requeued int, dead_lettered int)
language plpgsql
volatile
set search_path = public, pg_catalog
as $$
declare
    v_cutoff timestamptz := now() - make_interval(secs => p_lease_seconds);
    v_requeued int;
    v_dead int;
begin
    with dead_lettered as (
        update public.video_jobs
        set status = 'failed',
            error = 'video generation failed (lease expired after max attempts)',
            claimed_at = null,
            claimed_by = null,
            updated_at = now()
        where status not in ('queued', 'ready', 'failed', 'cancelled')
          and claimed_at is not null
          and claimed_at < v_cutoff
          and attempts >= p_max_attempts
        returning 1
    )
    select count(*)::int into v_dead from dead_lettered;

    with requeued as (
        update public.video_jobs
        set status = 'queued',
            claimed_at = null,
            claimed_by = null,
            updated_at = now()
        where status not in ('queued', 'ready', 'failed', 'cancelled')
          and claimed_at is not null
          and claimed_at < v_cutoff
          and attempts < p_max_attempts
        returning 1
    )
    select count(*)::int into v_requeued from requeued;

    return query select v_requeued, v_dead;
end;
$$;

-- The sweep is the worker's (service_role) alone. CREATE OR REPLACE preserves grants on an existing
-- function, but on a fresh install (db reset) it makes a NEW function that inherits Supabase's
-- default EXECUTE-to-authenticated grant — so re-assert the revokes to keep the posture explicit.
revoke execute on function public.requeue_stale_video_jobs(int, int) from public;
revoke execute on function public.requeue_stale_video_jobs(int, int) from anon;
revoke execute on function public.requeue_stale_video_jobs(int, int) from authenticated;
