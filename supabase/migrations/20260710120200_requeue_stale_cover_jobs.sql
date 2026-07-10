-- Course cover images (course-cover-images T1): the lease-recovery sweep — requeue cover jobs a
-- dead worker left in-flight past the lease, dead-letter those out of attempts. Mirrors
-- requeue_stale_video_jobs (20260617130000). Terminal statuses (queued/ready/failed/cancelled) are
-- excluded from the in-flight predicate so a settled or cancelled-but-still-leased job is never
-- resurrected. A live render's heartbeat keeps claimed_at fresh, so only genuinely stuck jobs match.
--
-- SECURITY INVOKER (the worker's supervisor calls it as service_role); VOLATILE; search_path pinned
-- as defence-in-depth (the body is fully schema-qualified). Dead-letter-before-requeue ordering and
-- idempotence match the video sweep.
--
-- To reverse: drop function if exists public.requeue_stale_cover_jobs(int, int);

create or replace function public.requeue_stale_cover_jobs(p_lease_seconds int, p_max_attempts int)
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
        update public.cover_jobs
        set status = 'failed',
            error = 'cover generation failed (lease expired after max attempts)',
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
        update public.cover_jobs
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

-- BLOCKING: revoke the default EXECUTE grants (PUBLIC + Supabase's anon/authenticated). The sweep is
-- the worker supervisor's (service_role) alone.
revoke execute on function public.requeue_stale_cover_jobs(int, int) from public;
revoke execute on function public.requeue_stale_cover_jobs(int, int) from anon;
revoke execute on function public.requeue_stale_cover_jobs(int, int) from authenticated;
