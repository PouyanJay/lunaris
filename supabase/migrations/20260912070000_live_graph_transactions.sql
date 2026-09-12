-- Graph-scoped leases protect the whole learner model across sessions and replicas.
-- Receipts contain only opaque operation hashes; expired paid work is not automatically repeated.
create table public.live_graph_leases (
    owner_id uuid references auth.users(id) on delete cascade,
    owner_key text generated always as (coalesce(owner_id::text, 'local')) stored,
    graph_id text not null check (length(graph_id) between 1 and 100),
    token uuid,
    expires_at timestamptz,
    paid_key text,
    primary key (owner_key, graph_id)
);
create table public.live_paid_operations (
    owner_id uuid references auth.users(id) on delete cascade,
    owner_key text generated always as (coalesce(owner_id::text, 'local')) stored,
    graph_id text not null check (length(graph_id) between 1 and 100),
    operation_key text not null check (operation_key ~ '^[a-f0-9]{64}$'),
    status text not null check (status in ('started', 'completed', 'indeterminate')),
    created_at timestamptz not null default now(),
    primary key (owner_key, graph_id, operation_key)
);
alter table public.live_graph_leases enable row level security;
alter table public.live_paid_operations enable row level security;
revoke all on public.live_graph_leases, public.live_paid_operations from public, anon, authenticated;
grant all on public.live_graph_leases, public.live_paid_operations to service_role;

create function public.acquire_live_graph(p_owner uuid, p_graph text) returns uuid
language plpgsql set search_path = '' as $$
declare
    v_owner text := coalesce(p_owner::text, 'local');
    v_row public.live_graph_leases;
    v_token uuid := gen_random_uuid();
begin
    insert into public.live_graph_leases (owner_id, graph_id) values (p_owner, p_graph)
        on conflict do nothing;
    select * into strict v_row from public.live_graph_leases
        where owner_key = v_owner and graph_id = p_graph for update;
    if v_row.token is not null and v_row.expires_at > clock_timestamp() then return null; end if;
    if v_row.paid_key is not null then
        update public.live_paid_operations set status = 'indeterminate'
            where owner_key = v_owner and graph_id = p_graph
            and operation_key = v_row.paid_key and status = 'started';
    end if;
    update public.live_graph_leases set token = v_token, paid_key = null,
        expires_at = clock_timestamp() + interval '120 seconds'
        where owner_key = v_owner and graph_id = p_graph;
    return v_token;
end;
$$;

create function public.lock_live_graph(p_owner uuid, p_graph text, p_token uuid)
returns public.live_graph_leases language plpgsql set search_path = '' as $$
declare v_row public.live_graph_leases;
begin
    select * into v_row from public.live_graph_leases
        where owner_key = coalesce(p_owner::text, 'local') and graph_id = p_graph for update;
    if not found or p_token is null or v_row.token is distinct from p_token
        or v_row.expires_at is null or v_row.expires_at <= clock_timestamp() then
        raise exception 'stale graph transaction claim';
    end if;
    return v_row;
end;
$$;

create function public.renew_live_graph(p_owner uuid, p_graph text, p_token uuid) returns boolean
language plpgsql set search_path = '' as $$
begin
    update public.live_graph_leases set expires_at = clock_timestamp() + interval '120 seconds'
        where owner_key = coalesce(p_owner::text, 'local') and graph_id = p_graph
        and token = p_token and expires_at > clock_timestamp();
    return found;
end;
$$;

create function public.begin_live_paid_operation(p_owner uuid, p_graph text, p_token uuid, p_operation text)
returns boolean language plpgsql set search_path = '' as $$
declare v_row public.live_graph_leases;
begin
    v_row := public.lock_live_graph(p_owner, p_graph, p_token);
    if v_row.paid_key = p_operation then return true; end if;
    if v_row.paid_key is not null then raise exception 'A paid operation is already active'; end if;
    insert into public.live_paid_operations(owner_id, graph_id, operation_key, status)
        values (p_owner, p_graph, p_operation, 'started') on conflict do nothing;
    if not found then return false; end if;
    update public.live_graph_leases set paid_key = p_operation
        where owner_key = v_row.owner_key and graph_id = p_graph;
    return true;
end;
$$;

create function public.commit_live_graph(p_owner uuid, p_graph text, p_token uuid, p_change jsonb)
returns boolean language plpgsql set search_path = '' as $$
declare
    v_row public.live_graph_leases;
    v_session jsonb := p_change -> 'session';
    v_model jsonb := p_change -> 'knowledge';
    v_node record;
    v_create boolean := coalesce((p_change ->> 'create')::boolean, false);
    v_forget boolean := coalesce((p_change ->> 'forget')::boolean, false);
    v_delete text := p_change ->> 'delete_session';
begin
    v_row := public.lock_live_graph(p_owner, p_graph, p_token);
    if v_forget then
        if exists(select 1 from public.live_sessions where user_id is not distinct from p_owner
            and graph_id = p_graph and status not in ('closed', 'abandoned')) then
            raise exception 'An open session prevents forgetting this graph';
        end if;
        delete from public.live_knowledge where user_id is not distinct from p_owner and graph_id = p_graph;
    elsif v_delete is not null then
        delete from public.live_sessions where id = v_delete
            and user_id is not distinct from p_owner and graph_id = p_graph;
        if not found then raise exception 'stale session deletion'; end if;
    elsif v_session is not null and v_session <> 'null'::jsonb then
        if v_session ->> 'graphId' is distinct from p_graph then raise exception 'Invalid graph scope'; end if;
        if v_create then
            insert into public.live_sessions(id, user_id, graph_id, status, turn_count, payload)
                values (v_session ->> 'sessionId', p_owner, p_graph, v_session ->> 'status',
                    jsonb_array_length(v_session -> 'turns'), v_session);
        else
            update public.live_sessions set status = v_session ->> 'status',
                turn_count = jsonb_array_length(v_session -> 'turns'), payload = v_session
                where id = v_session ->> 'sessionId' and user_id is not distinct from p_owner
                and graph_id = p_graph and turn_count = (p_change ->> 'expected_turns')::integer;
            if not found then raise exception 'stale session transaction'; end if;
        end if;
        if v_model is not null and v_model <> 'null'::jsonb then
            if v_model ->> 'graphId' is distinct from p_graph then raise exception 'Invalid knowledge scope'; end if;
            for v_node in select key, value from jsonb_each(v_model -> 'nodes') loop
                if v_node.value ->> 'nodeId' is distinct from v_node.key then raise exception 'Invalid node identity'; end if;
                insert into public.live_knowledge(user_id, graph_id, node_id, estimate, evidence_count,
                    last_evidence_turn, prior, review_stage, due_at)
                    values (p_owner, p_graph, v_node.key, (v_node.value ->> 'estimate')::double precision,
                        (v_node.value ->> 'evidenceCount')::integer,
                        coalesce((v_node.value ->> 'lastEvidenceTurn')::integer, 0),
                        (v_node.value ->> 'prior')::double precision,
                        coalesce((v_node.value ->> 'reviewStage')::integer, 0),
                        (v_node.value ->> 'dueAt')::timestamptz)
                    on conflict(user_id, graph_id, node_id) do update set
                        estimate = excluded.estimate, evidence_count = excluded.evidence_count,
                        last_evidence_turn = excluded.last_evidence_turn, prior = excluded.prior,
                        review_stage = excluded.review_stage, due_at = excluded.due_at, updated_at = now();
            end loop;
        end if;
    else
        raise exception 'Invalid empty session transaction';
    end if;
    update public.live_paid_operations set status = 'completed'
        where owner_key = v_row.owner_key and graph_id = p_graph and operation_key = v_row.paid_key;
    update public.live_graph_leases set paid_key = null
        where owner_key = v_row.owner_key and graph_id = p_graph;
    return true;
end;
$$;

create function public.release_live_graph(p_owner uuid, p_graph text, p_token uuid) returns boolean
language plpgsql set search_path = '' as $$
declare v_row public.live_graph_leases;
begin
    select * into v_row from public.live_graph_leases
        where owner_key = coalesce(p_owner::text, 'local') and graph_id = p_graph for update;
    if not found or p_token is null or v_row.token is distinct from p_token then return false; end if;
    update public.live_paid_operations set status = 'indeterminate'
        where owner_key = v_row.owner_key and graph_id = p_graph
        and operation_key = v_row.paid_key and status = 'started';
    update public.live_graph_leases set token = null, expires_at = null, paid_key = null
        where owner_key = v_row.owner_key and graph_id = p_graph;
    return true;
end;
$$;

revoke all on function public.acquire_live_graph(uuid, text) from public, anon, authenticated;
revoke all on function public.lock_live_graph(uuid, text, uuid) from public, anon, authenticated;
revoke all on function public.renew_live_graph(uuid, text, uuid) from public, anon, authenticated;
revoke all on function public.begin_live_paid_operation(uuid, text, uuid, text) from public, anon, authenticated;
revoke all on function public.commit_live_graph(uuid, text, uuid, jsonb) from public, anon, authenticated;
revoke all on function public.release_live_graph(uuid, text, uuid) from public, anon, authenticated;
grant execute on function public.acquire_live_graph(uuid, text) to service_role;
grant execute on function public.lock_live_graph(uuid, text, uuid) to service_role;
grant execute on function public.renew_live_graph(uuid, text, uuid) to service_role;
grant execute on function public.begin_live_paid_operation(uuid, text, uuid, text) to service_role;
grant execute on function public.commit_live_graph(uuid, text, uuid, jsonb) to service_role;
grant execute on function public.release_live_graph(uuid, text, uuid) to service_role;
