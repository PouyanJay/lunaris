-- API requests contain trusted graph excerpts, never executable generated code.
-- A separate supervisor claims once and runs the existing isolated verifier appliance.
create table public.live_sim_requests (
    owner_id uuid not null references auth.users(id) on delete cascade,
    cache_key text not null check (cache_key ~ '^[a-f0-9]{64}$'),
    session_id text not null references public.live_sessions(id) on delete cascade,
    request jsonb not null check (jsonb_typeof(request) = 'object' and octet_length(request::text) <= 40000),
    created_at timestamptz not null default now(),
    claimed_at timestamptz,
    primary key(owner_id, cache_key)
);
alter table public.live_sim_requests enable row level security;
revoke all on public.live_sim_requests from public, anon, authenticated;
grant all on public.live_sim_requests to service_role;
create index live_sim_requests_pending on public.live_sim_requests(created_at) where claimed_at is null;

create function public.enqueue_live_sim(p_owner uuid, p_session text, p_key text, p_request jsonb)
returns text language plpgsql set search_path = '' as $$
declare v_session public.live_sessions; v_build public.live_sim_builds;
    v_request public.live_sim_requests;
begin
    -- Serialize quota checks for this owner, including requests from separate API replicas.
    perform pg_advisory_xact_lock(hashtextextended(p_owner::text, 736));
    select * into v_session from public.live_sessions where id=p_session and user_id=p_owner;
    if not found then raise exception 'No such session'; end if;
    if v_session.status not in ('active','placing','warming') then return 'unavailable'; end if;
    select * into v_build from public.live_sim_builds where owner_id=p_owner and cache_key=p_key;
    if found then
        return case when v_build.status='building' and v_build.expires_at<=clock_timestamp()
            then 'indeterminate' else v_build.status end;
    end if;
    select * into v_request from public.live_sim_requests
        where owner_id=p_owner and cache_key=p_key for update;
    if found then
        if v_request.claimed_at is not null then return 'indeterminate'; end if;
        if v_request.created_at <= now()-interval '10 minutes' or not exists(
            select 1 from public.live_sessions where id=v_request.session_id
            and status in ('active','placing','warming')
        ) then
            if v_request.session_id <> p_session and (select count(*) from public.live_sim_requests
                where owner_id=p_owner and session_id=p_session)>=2 then return 'unavailable'; end if;
            -- No build claim exists, so no paid call was admitted. It is safe to refresh this request.
            update public.live_sim_requests set session_id=p_session, request=p_request, created_at=now()
                where owner_id=p_owner and cache_key=p_key;
        end if;
        return 'queued';
    end if;
    if (select count(*) from public.live_sim_requests where owner_id=p_owner and session_id=p_session)>=2
        or (select count(*) from (
            select cache_key from public.live_sim_requests where owner_id=p_owner
                and created_at >= now()-interval '24 hours'
            union
            select cache_key from public.live_sim_builds where owner_id=p_owner
                and created_at >= now()-interval '24 hours'
        ) admissions)>=10 then return 'unavailable'; end if;
    insert into public.live_sim_requests(owner_id, cache_key, session_id, request)
        values(p_owner,p_key,p_session,p_request);
    return 'queued';
end;
$$;

create function public.take_live_sim_request() returns jsonb
language plpgsql set search_path = '' as $$
declare v_request public.live_sim_requests; v_claim jsonb;
begin
    select r.* into v_request from public.live_sim_requests r
        join public.live_sessions s on s.id=r.session_id and s.user_id=r.owner_id
        where r.claimed_at is null and r.created_at > now()-interval '10 minutes'
        and s.status in ('active','placing','warming')
        order by r.created_at for update of r skip locked limit 1;
    if not found then return null; end if;
    v_claim := public.claim_live_sim(v_request.owner_id, null, v_request.cache_key);
    update public.live_sim_requests set claimed_at=clock_timestamp()
        where owner_id=v_request.owner_id and cache_key=v_request.cache_key;
    if not (v_claim ? 'token') then return null; end if;
    return to_jsonb(v_request) || jsonb_build_object('token',v_claim->>'token');
end;
$$;

revoke all on function public.enqueue_live_sim(uuid,text,text,jsonb) from public,anon,authenticated;
revoke all on function public.take_live_sim_request() from public,anon,authenticated;
grant execute on function public.enqueue_live_sim(uuid,text,text,jsonb) to service_role;
grant execute on function public.take_live_sim_request() to service_role;
