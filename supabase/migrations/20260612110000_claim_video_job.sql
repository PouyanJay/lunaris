-- Explainer-video V0-T1: the atomic claim — FOR UPDATE SKIP LOCKED behind a service-only RPC.
--
-- PostgREST cannot express row locks, so the queue's claim lives in the database: one call
-- atomically picks the oldest 'queued' job, locks it (skipping rows other workers already hold),
-- flips it to 'planning' (the first in-flight stage), stamps the lease (claimed_at / claimed_by /
-- attempts), and returns the row. Two concurrent claimers can never get the same job — the row
-- lock arbitrates, not app code. The worker calls this via supabase-py rpc() as service_role.
--
-- Everything is schema-qualified, so a mutable search_path has nothing to bite on.
--
-- To reverse: drop function if exists public.claim_video_job(text);

-- SECURITY INVOKER is intentional: the sole caller is the backend service_role client, which
-- already holds full table access — DEFINER would add privilege with no benefit. VOLATILE is the
-- default for a writing function; declared explicitly so intent reads off the header. The
-- search_path pin matches the repo's function pattern (defence-in-depth; the body is fully
-- schema-qualified anyway).
create or replace function public.claim_video_job(p_worker text)
returns setof public.video_jobs
language sql
volatile
set search_path = public, pg_catalog
as $$
    update public.video_jobs
    set status = 'planning',
        claimed_at = now(),
        claimed_by = p_worker,
        attempts = attempts + 1,
        updated_at = now()
    where id = (
        select id
        from public.video_jobs
        where status = 'queued'
        order by created_at
        for update skip locked
        limit 1
    )
    returning *;
$$;

-- BLOCKING: PostgreSQL grants EXECUTE to PUBLIC by default, and Supabase grants it to anon +
-- authenticated. The claim is the worker's (service_role) alone — revoke from all three and
-- grant to no one (mirrors match_grounding_documents).
revoke execute on function public.claim_video_job(text) from public;
revoke execute on function public.claim_video_job(text) from anon;
revoke execute on function public.claim_video_job(text) from authenticated;
