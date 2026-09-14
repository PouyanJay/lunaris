-- Rollback: disable voice, remove generated PCM through Storage API, then drop voice tables/functions.
-- Admission serializes on the session row against turn commits, closure and deletion.
-- Reservations are conservative voice-only ceilings, retained even for uncertain provider outcomes.
create table public.live_voice_operations (
    session_id text not null references public.live_sessions(id) on delete cascade,
    owner_id uuid references auth.users(id) on delete cascade,
    operation_id uuid not null,
    kind text not null check (kind in ('transcription', 'speech')),
    fingerprint text not null check (fingerprint ~ '^[a-f0-9]{64}$'),
    turn_seq integer not null check (turn_seq > 0),
    source_run_id text not null check (length(source_run_id) between 1 and 100),
    exchange_sequence integer check (exchange_sequence between 1 and 20),
    reserve_usd numeric not null check (reserve_usd > 0 and reserve_usd <= 3),
    token uuid not null,
    session_seconds integer not null check (session_seconds between 1 and 3600),
    status text not null default 'started' check (status in ('started','completed','indeterminate')),
    audio_key text check (audio_key ~ '^[a-f0-9]{32}\.pcm$'),
    result jsonb check (result is null or pg_column_size(result) <= 20000),
    created_at timestamptz not null default clock_timestamp(),
    expires_at timestamptz not null,
    primary key (session_id, operation_id)
);
-- Tombstones deliberately have no FK: deleting session/user must not forget storage cleanup.
create table public.live_voice_audio_cleanup (
    object_key text primary key check (object_key ~ '^[a-f0-9]{32}\.pcm$'),
    cleanup_after timestamptz not null,
    created_at timestamptz not null default clock_timestamp()
);
create index live_voice_audio_cleanup_due on public.live_voice_audio_cleanup(cleanup_after);
alter table public.live_voice_operations enable row level security;
alter table public.live_voice_audio_cleanup enable row level security;
revoke all on public.live_voice_operations, public.live_voice_audio_cleanup from public, anon, authenticated;
grant all on public.live_voice_operations, public.live_voice_audio_cleanup to service_role;

insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
    values('live-voice','live-voice',false,11520000,array['audio/pcm']) on conflict(id) do update set public=false, file_size_limit=11520000, allowed_mime_types=array['audio/pcm'];

create function public.live_voice_source(p_session public.live_sessions, p_request jsonb, p_seconds integer)
returns text language plpgsql set search_path = '' as $$
declare v_turn jsonb; v_exchange integer := (p_request->>'exchange_sequence')::integer;
begin
    if p_session.status = 'abandoned' or jsonb_array_length(p_session.payload->'turns') < 1
        or p_session.payload->'turns' is null then return null; end if;
    if p_session.status in ('active','placing') and
        (p_session.payload->>'startedAt' is null or (p_session.payload->>'startedAt')::timestamptz
            + make_interval(secs => p_seconds) <= clock_timestamp()) then return null; end if;
    if p_request->>'kind' = 'transcription' and
        (p_session.status not in ('active','placing') or v_exchange is not null) then return null; end if;
    v_turn := p_session.payload->'turns'->-1;
    if (v_turn->>'seq')::integer is distinct from (p_request->>'turn_seq')::integer
        or v_turn->>'runId' is distinct from p_request->>'source_run_id'
        or (v_turn->>'answer') is not null then return null; end if;
    if v_exchange is not null then
        if v_exchange not between 1 and 20 or v_exchange is distinct from
            jsonb_array_length(coalesce(v_turn->'simExchanges','[]'::jsonb)) then return null; end if;
        return v_turn->'simExchanges'->-1->'reaction'->>'text';
    end if;
    return v_turn->>'tutor';
end;
$$;
revoke execute on function public.live_voice_source(public.live_sessions,jsonb,integer) from public,anon,authenticated;
grant execute on function public.live_voice_source(public.live_sessions,jsonb,integer) to service_role;

create function public.claim_live_voice(p_owner uuid, p_session text, p_request jsonb)
returns jsonb language plpgsql set search_path = '' as $$
declare
    v_session public.live_sessions; v_entry public.live_voice_operations;
    v_text text; v_token uuid := gen_random_uuid(); v_audio text;
    v_concurrency integer := coalesce((p_request->>'concurrency')::integer,2);
    v_operations integer := coalesce((p_request->>'operations')::integer,120);
    v_budget numeric := coalesce((p_request->>'budget_usd')::numeric,3);
    v_seconds integer := coalesce((p_request->>'session_seconds')::integer,1800);
    v_lease integer := coalesce((p_request->>'lease_seconds')::integer,120);
    v_reserve numeric := (p_request->>'reserve_usd')::numeric;
begin
    if v_concurrency not between 1 and 2 or v_operations not between 1 and 120
        or v_budget not between 0.000001 and 3 or v_seconds not between 1 and 3600
        or v_lease not between 1 and 120 or v_reserve is null or not (v_reserve > 0 and v_reserve <= 3)
        or p_request->>'kind' is null or p_request->>'kind' not in ('transcription','speech')
        or p_request->>'fingerprint' is null or p_request->>'fingerprint' !~ '^[a-f0-9]{64}$'
        or p_request->>'operation_id' is null then raise exception 'Invalid voice admission'; end if;
    select * into v_session from public.live_sessions where id=p_session
        and user_id is not distinct from p_owner for update;
    if not found then return jsonb_build_object('status','missing'); end if;
    v_text := public.live_voice_source(v_session,p_request,v_seconds);
    if v_text is null then return jsonb_build_object('status','stale'); end if;
    update public.live_voice_operations set status='indeterminate' where session_id=p_session
        and status='started' and expires_at <= clock_timestamp();
    select * into v_entry from public.live_voice_operations where session_id=p_session
        and operation_id=(p_request->>'operation_id')::uuid;
    if found then
        if v_entry.owner_id is distinct from p_owner or v_entry.kind <> p_request->>'kind'
            or v_entry.fingerprint <> p_request->>'fingerprint'
            or v_entry.turn_seq is distinct from (p_request->>'turn_seq')::integer
            or v_entry.source_run_id is distinct from p_request->>'source_run_id'
            or v_entry.exchange_sequence is distinct from (p_request->>'exchange_sequence')::integer
            then return jsonb_build_object('status','conflict'); end if;
        if v_entry.status='completed' then
            if v_entry.created_at + interval '1 day' <= clock_timestamp() then
                return jsonb_build_object('status','unavailable'); end if;
            return jsonb_build_object('status','completed','result',v_entry.result);
        end if;
        return jsonb_build_object('status',case when v_entry.status='started' then 'in_progress' else 'indeterminate' end);
    end if;
    if (select count(*) from public.live_voice_operations where session_id=p_session) >= v_operations
        or (select count(*) from public.live_voice_operations where session_id=p_session and status='started') >= v_concurrency
        or (select coalesce(sum(reserve_usd),0) from public.live_voice_operations where session_id=p_session) + v_reserve > v_budget
        then return jsonb_build_object('status','unavailable'); end if;
    if p_request->>'kind'='speech' then
        v_audio := replace(gen_random_uuid()::text,'-','') || '.pcm';
        insert into public.live_voice_audio_cleanup(object_key,cleanup_after) values(v_audio,clock_timestamp()+interval '1 day');
    end if;
    insert into public.live_voice_operations(session_id,owner_id,operation_id,kind,fingerprint,
        turn_seq,source_run_id,exchange_sequence,reserve_usd,token,expires_at,audio_key,session_seconds)
        values(p_session,p_owner,(p_request->>'operation_id')::uuid,p_request->>'kind',p_request->>'fingerprint',
            (p_request->>'turn_seq')::integer,p_request->>'source_run_id',(p_request->>'exchange_sequence')::integer,
            v_reserve,v_token,clock_timestamp()+make_interval(secs=>v_lease),v_audio,v_seconds);
    return jsonb_build_object('status','started','token',v_token,'source_text',v_text,'audio_key',v_audio);
end;
$$;
revoke execute on function public.claim_live_voice(uuid,text,jsonb) from public,anon,authenticated;
grant execute on function public.claim_live_voice(uuid,text,jsonb) to service_role;

create function public.finish_live_voice(p_owner uuid,p_session text,p_operation uuid,p_token uuid,p_result jsonb)
returns boolean language plpgsql set search_path = '' as $$
declare v_session public.live_sessions; v_entry public.live_voice_operations; v_source jsonb;
begin
    select * into v_session from public.live_sessions where id=p_session
        and user_id is not distinct from p_owner for update;
    if not found then return false; end if;
    select * into v_entry from public.live_voice_operations where session_id=p_session
        and operation_id=p_operation and owner_id is not distinct from p_owner;
    if not found or v_entry.token is distinct from p_token or v_entry.status <> 'started'
        or v_entry.expires_at <= clock_timestamp() then return false; end if;
    v_source := jsonb_build_object('kind',v_entry.kind,'turn_seq',v_entry.turn_seq,
        'source_run_id',v_entry.source_run_id,'exchange_sequence',v_entry.exchange_sequence);
    -- Completion checks lifecycle and current source again; the original admission owns its deadline.
    if public.live_voice_source(v_session,v_source,v_entry.session_seconds) is null then return false; end if;
    if p_result is not null then
        if jsonb_typeof(p_result) <> 'object' or pg_column_size(p_result)>20000
            or (p_result - array['text','provider','model','audio_key','audio_bytes','sample_rate']) <> '{}'::jsonb
            or length(coalesce(p_result->>'provider','')) not between 1 and 100
            or length(coalesce(p_result->>'model','')) not between 1 and 100
            then return false; end if;
        if v_entry.kind='transcription' then
            if p_result->>'text' is null or length(p_result->>'text') not between 1 and 4000
                or p_result->>'audio_key' is not null or p_result->>'audio_bytes' is not null
                or p_result->>'sample_rate' is not null then return false; end if;
        else
            if p_result->>'audio_key' is distinct from v_entry.audio_key or p_result->>'text' is not null
                or (p_result->>'audio_bytes') is null or (p_result->>'sample_rate') is null
                or (p_result->>'audio_bytes')::integer not between 2 and 11520000
                or (p_result->>'audio_bytes')::integer % 2 <> 0 or (p_result->>'sample_rate')::integer <> 24000
                then return false; end if;
        end if;
    end if;
    update public.live_voice_operations set status=case when p_result is null then 'indeterminate' else 'completed' end,
        result=p_result where session_id=p_session and operation_id=p_operation;
    return true;
end;
$$;
revoke execute on function public.finish_live_voice(uuid,text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.finish_live_voice(uuid,text,uuid,uuid,jsonb) to service_role;

create function public.expire_live_voice_audio() returns trigger
language plpgsql set search_path = '' as $$
begin
    -- A deleted in-flight claim may have an upload in progress. Uploads are bounded to 60 seconds;
    -- leave five minutes after deletion/lease expiry before cleanup to avoid a late-upload orphan.
    update public.live_voice_audio_cleanup set cleanup_after=case when old.status='completed'
        then clock_timestamp() else greatest(clock_timestamp(),old.expires_at)+interval '5 minutes' end
        where object_key=old.audio_key;
    return old;
end;
$$;
revoke execute on function public.expire_live_voice_audio() from public,anon,authenticated;
create trigger live_voice_audio_deleted before delete on public.live_voice_operations
    for each row execute function public.expire_live_voice_audio();

create function public.due_live_voice_audio_cleanup() returns jsonb
language plpgsql set search_path = '' as $$
declare v_result jsonb;
begin
    -- Keep admission receipts/budget, discard derived learner text when its replay window expires.
    update public.live_voice_operations set result=null where created_at+interval '1 day' <= clock_timestamp()
        and result is not null;
    select coalesce(jsonb_agg(jsonb_build_object('object_key',q.object_key)),'[]'::jsonb) into v_result
        from (select object_key from public.live_voice_audio_cleanup where cleanup_after <= clock_timestamp()
            order by cleanup_after limit 100) q;
    return v_result;
end;
$$;
revoke execute on function public.due_live_voice_audio_cleanup() from public,anon,authenticated;
grant execute on function public.due_live_voice_audio_cleanup() to service_role;

create function public.ack_live_voice_audio_cleanup(p_key text) returns void
language sql set search_path = '' as $$
    delete from public.live_voice_audio_cleanup where object_key=p_key and cleanup_after <= clock_timestamp();
$$;
revoke execute on function public.ack_live_voice_audio_cleanup(text) from public,anon,authenticated;
grant execute on function public.ack_live_voice_audio_cleanup(text) to service_role;
