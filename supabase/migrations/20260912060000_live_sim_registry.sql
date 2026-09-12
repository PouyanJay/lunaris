-- Generated code is immutable, owner-scoped by default, and only published through a fenced build.
-- A public source is an explicit trusted operator decision; user graph jobs never supply one.
create table public.live_sim_builds (
    owner_id uuid references auth.users(id) on delete cascade,
    public_source text check (length(public_source) between 1 and 1000),
    scope_key text generated always as
        (case when public_source is not null then 'public' else coalesce(owner_id::text, 'local') end) stored,
    cache_key text not null check (cache_key ~ '^[a-f0-9]{64}$'),
    token uuid not null default gen_random_uuid(),
    status text not null default 'building' check (status in ('building', 'approved', 'rejected', 'indeterminate')),
    expires_at timestamptz not null default (now() + interval '300 seconds'),
    result jsonb,
    created_at timestamptz not null default now(),
    primary key (scope_key, cache_key),
    check (owner_id is null or public_source is null)
);

create table public.live_sim_assets (
    id uuid primary key,
    owner_id uuid references auth.users(id) on delete cascade,
    public_source text check (length(public_source) between 1 and 1000),
    scope_key text generated always as
        (case when public_source is not null then 'public' else coalesce(owner_id::text, 'local') end) stored,
    cache_key text not null check (cache_key ~ '^[a-f0-9]{64}$'),
    content_hash text not null check (content_hash ~ '^[a-f0-9]{64}$'),
    payload jsonb not null,
    revoked boolean not null default false,
    created_at timestamptz not null default now(),
    unique (scope_key, cache_key),
    check (owner_id is null or public_source is null)
);

alter table public.live_sim_builds enable row level security;
alter table public.live_sim_assets enable row level security;
revoke all on public.live_sim_builds, public.live_sim_assets from public, anon, authenticated;
grant all on public.live_sim_builds, public.live_sim_assets to service_role;
grant select on public.live_sim_assets to authenticated;
create policy live_sim_assets_read on public.live_sim_assets for select to authenticated
    using (not revoked and (owner_id = (select auth.uid()) or public_source is not null));
create index live_sim_assets_owner on public.live_sim_assets (owner_id) where not revoked;

create function public.preserve_live_sim_asset() returns trigger
language plpgsql set search_path = '' as $$
begin
    if (to_jsonb(new) - 'revoked' - 'scope_key') is distinct from
        (to_jsonb(old) - 'revoked' - 'scope_key') then
        raise exception 'Simulator assets are immutable';
    end if;
    if old.revoked and not new.revoked then
        raise exception 'Revocation is permanent; publish a new version';
    end if;
    return new;
end;
$$;
create trigger live_sim_asset_immutable before update on public.live_sim_assets
    for each row execute function public.preserve_live_sim_asset();
revoke all on function public.preserve_live_sim_asset() from public, anon, authenticated;

create function public.claim_live_sim(p_owner uuid, p_public_source text, p_cache_key text)
returns jsonb language plpgsql set search_path = '' as $$
declare
    v_scope text := case when p_public_source is not null then 'public' else coalesce(p_owner::text, 'local') end;
    v_row public.live_sim_builds;
    v_created boolean;
begin
    insert into public.live_sim_builds (owner_id, public_source, cache_key)
        values (p_owner, p_public_source, p_cache_key) on conflict do nothing;
    v_created := found;
    select * into strict v_row from public.live_sim_builds
        where scope_key = v_scope and cache_key = p_cache_key for update;
    if v_created then
        return jsonb_build_object('status', 'building', 'token', v_row.token);
    end if;
    -- A crashed potentially paid call is not a license to start another paid call.
    if v_row.status = 'building' and v_row.expires_at <= clock_timestamp() then
        update public.live_sim_builds set status = 'indeterminate'
            where scope_key = v_scope and cache_key = p_cache_key;
        return jsonb_build_object('status', 'indeterminate');
    end if;
    return jsonb_build_object('status', v_row.status);
end;
$$;

create function public.finish_live_sim(
    p_owner uuid, p_public_source text, p_cache_key text, p_token uuid, p_status text, p_asset jsonb
) returns boolean language plpgsql set search_path = '' as $$
declare
    v_scope text := case when p_public_source is not null then 'public' else coalesce(p_owner::text, 'local') end;
    v_row public.live_sim_builds;
    v_hash text;
begin
    select * into v_row from public.live_sim_builds
        where scope_key = v_scope and cache_key = p_cache_key for update;
    if not found or v_row.token is distinct from p_token or v_row.status <> 'building'
        or v_row.expires_at <= clock_timestamp()
        or v_row.owner_id is distinct from p_owner
        or v_row.public_source is distinct from p_public_source then
        raise exception 'stale simulator build claim';
    end if;
    if p_status not in ('approved', 'rejected', 'indeterminate') then
        raise exception 'Invalid build outcome';
    end if;
    if p_status = 'approved' then
        v_hash := encode(sha256(convert_to(p_asset #>> '{bundle,candidate,html}', 'UTF8')), 'hex');
        if v_hash is null
            or p_asset ->> 'cacheKey' is distinct from p_cache_key
            or (p_asset ->> 'ownerId')::uuid is distinct from p_owner
            or p_asset ->> 'publicSource' is distinct from p_public_source
            or p_asset ->> 'revoked' is distinct from 'false'
            or p_asset #>> '{bundle,report,approved}' is distinct from 'true'
            or p_asset #> '{bundle,report,reasons}' is distinct from '[]'::jsonb
            or p_asset #>> '{bundle,report,contentHash}' is distinct from v_hash
            or p_asset #>> '{bundle,visualVerdict,passed}' is distinct from 'true'
            or p_asset #>> '{bundle,visualVerdict,contentHash}' is distinct from v_hash then
            raise exception 'Invalid simulator publication evidence or scope';
        end if;
        insert into public.live_sim_assets
            (id, owner_id, public_source, cache_key, content_hash, payload)
            values ((p_asset ->> 'id')::uuid, p_owner, p_public_source, p_cache_key, v_hash, p_asset);
    end if;
    update public.live_sim_builds set status = p_status, result = p_asset
        where scope_key = v_scope and cache_key = p_cache_key;
    return true;
end;
$$;

revoke all on function public.claim_live_sim(uuid, text, text) from public, anon, authenticated;
revoke all on function public.finish_live_sim(uuid, text, text, uuid, text, jsonb) from public, anon, authenticated;
grant execute on function public.claim_live_sim(uuid, text, text) to service_role;
grant execute on function public.finish_live_sim(uuid, text, text, uuid, text, jsonb) to service_role;
