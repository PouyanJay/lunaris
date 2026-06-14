-- Explainer-video V7-T4: the lease-timeout sweep — requeue stuck jobs, dead-letter the exhausted.
--
-- A worker claims a job (claim_video_job stamps claimed_at + bumps attempts) and heartbeats while it
-- renders, so claimed_at stays fresh for a live render. If the worker DIES mid-render the job is left
-- in an in-flight state (planning…assembling) with a stale claimed_at and never settles. This sweep
-- (run periodically by every worker replica, and woken from scale-to-zero by the KEDA scaler, which
-- counts stale in-flight rows as well as queued ones) recovers them:
--   • attempts >= cap  → dead-letter (status='failed') so a poison job can't loop forever;
--   • attempts <  cap  → requeue (status='queued', lease cleared) for a fresh claim.
-- Dead-lettering runs first so a row past the cap isn't requeued in the same pass. Idempotent: a
-- second concurrent sweep finds nothing already-acted-on (the WHERE no longer matches).
--
-- To reverse: drop function if exists public.requeue_stale_video_jobs(int, int);

-- SECURITY INVOKER (the sole caller is the service_role worker, which already holds full table
-- access). VOLATILE (it writes). search_path pinned + body fully schema-qualified — same pattern as
-- claim_video_job. Returns the two counts so the worker can log what it recovered.
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
        where status not in ('queued', 'ready', 'failed')
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
        where status not in ('queued', 'ready', 'failed')
          and claimed_at is not null
          and claimed_at < v_cutoff
          and attempts < p_max_attempts
        returning 1
    )
    select count(*)::int into v_requeued from requeued;

    return query select v_requeued, v_dead;
end;
$$;

-- The sweep is the worker's (service_role) alone — revoke EXECUTE from PUBLIC + anon + authenticated
-- and grant to no one (mirrors claim_video_job / match_grounding_documents).
revoke execute on function public.requeue_stale_video_jobs(int, int) from public;
revoke execute on function public.requeue_stale_video_jobs(int, int) from anon;
revoke execute on function public.requeue_stale_video_jobs(int, int) from authenticated;
