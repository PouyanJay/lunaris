-- Course cover images (course-cover-images T0/T1): the atomic claim — FOR UPDATE SKIP LOCKED behind
-- a service-only RPC (mirrors claim_video_job, 20260612110000).
--
-- PostgREST cannot express row locks, so the queue's claim lives in the database: one call
-- atomically picks the oldest 'queued' cover job, locks it (skipping rows other workers already
-- hold), flips it to 'art_directing' (the first in-flight stage — Claude writes the house-style
-- prompt), stamps the lease (claimed_at / claimed_by / attempts), and returns the row. Two
-- concurrent claimers can never get the same job. The worker calls this via supabase-py rpc() as
-- service_role.
--
-- To reverse: drop function if exists public.claim_cover_job(text);

-- SECURITY INVOKER is intentional: the sole caller is the backend service_role client, which
-- already holds full table access. VOLATILE (default for a writing function) declared explicitly;
-- search_path pinned as defence-in-depth (the body is fully schema-qualified anyway).
create or replace function public.claim_cover_job(p_worker text)
returns setof public.cover_jobs
language sql
volatile
set search_path = public, pg_catalog
as $$
    update public.cover_jobs
    set status = 'art_directing',
        claimed_at = now(),
        claimed_by = p_worker,
        attempts = attempts + 1,
        updated_at = now()
    where id = (
        select id
        from public.cover_jobs
        where status = 'queued'
        order by created_at
        for update skip locked
        limit 1
    )
    returning *;
$$;

-- BLOCKING: revoke the default EXECUTE grants (PUBLIC + Supabase's anon/authenticated). The claim is
-- the worker's (service_role) alone — revoke from all three and grant to no one.
revoke execute on function public.claim_cover_job(text) from public;
revoke execute on function public.claim_cover_job(text) from anon;
revoke execute on function public.claim_cover_job(text) from authenticated;
