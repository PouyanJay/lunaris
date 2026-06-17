-- Signup invite-key gate: a single shared invitation code, enforced server-side in Supabase Auth.
--
-- Signup is browser-direct (`supabase.auth.signUp()` with the public anon key), so a check done only
-- in the web form is bypassable. The real gate is a Before-User-Created auth hook — a Postgres
-- function GoTrue calls server-side before inserting the user. The function reads the singleton
-- `signup_gate` row and rejects the signup when the `invite_code` the form passed as user metadata
-- doesn't match the stored code (and the gate is enforced).
--
-- Single shared code (not per-invite) by product decision; the table is shaped so per-invite codes /
-- usage counts / expiry can be added later without a rewrite.
--
-- Access posture: the code is a low-value shared secret the admin hands out, but the SPA must never
-- read it directly. RLS enabled + forced + grants revoked, so the table is reachable only by (a) the
-- backend service-role client (admin screen read/write — service_role bypasses RLS by role
-- attribute) and (b) the auth hook, which runs as `supabase_auth_admin` and is granted a read-only
-- foothold (select grant + a select-only policy) — the canonical Supabase auth-hook pattern.
--
-- To reverse:
--   drop function if exists public.before_user_created_invite_gate(jsonb);
--   drop table if exists public.signup_gate;

create table if not exists public.signup_gate (
    -- Singleton: `id` can only ever be `true`, so the table holds at most one row. The admin API
    -- upserts/updates this row; reads take it directly.
    id          boolean primary key default true check (id),
    invite_code text        not null,
    -- When false the gate is open (any signup allowed); the admin "Require invitation code" toggle.
    enforced    boolean     not null default true,
    updated_at  timestamptz not null default now(),
    -- The admin's auth.uid() at the last change — a stamp, not an FK: the singleton settings row
    -- outlives any single admin account, so it is intentionally not tied to auth.users.
    updated_by  uuid
);

-- RLS (BLOCKING): enabled + forced, no anon/authenticated access. The admin screen reaches the row
-- through the service-role client (bypasses RLS); the hook reaches it through the policy below.
alter table public.signup_gate enable row level security;

-- FORCE so even the table owner / `postgres` superuser session goes through RLS — a direct
-- psql/`db query` path as postgres can't read the code. service_role still bypasses by role
-- attribute (the backend admin API legitimately uses it); supabase_auth_admin reads via its policy.
alter table public.signup_gate force row level security;

-- Defense in depth: revoke the default grants Supabase hands anon + authenticated on every public
-- table, so the SPA's anon/user JWT clients have no path to the code even if RLS were ever toggled
-- off by mistake.
revoke all on table public.signup_gate from public, anon, authenticated;

-- The auth hook runs as `supabase_auth_admin`; give it the minimum to read the gate row.
grant usage on schema public to supabase_auth_admin;
grant select on table public.signup_gate to supabase_auth_admin;

create policy signup_gate_auth_admin_read on public.signup_gate
    as permissive for select to supabase_auth_admin using (true);

-- The Before-User-Created hook. Input: { "user": { "user_metadata": {...}, ... }, "metadata": {...} }
-- where `user_metadata` is what `signUp({ options: { data } })` set. Returns `{}` to allow the
-- signup, or `{ "error": { "http_code", "message" } }` to reject it.
--
-- SECURITY NOTES (invoker rights — deliberately NOT security definer):
--   - Runs as the calling `supabase_auth_admin`, which already has SELECT on this table via the
--     grant + policy above — so no privilege elevation is needed or wanted.
--   - search_path pinned (public, pg_catalog) — no schema-shadowing of built-ins.
--   - No dynamic SQL; the event is read only via the `#>>` path operator (no injection surface).
--   - The only attacker-controlled value is the submitted code; it is compared to the trusted DB
--     value, never executed.
--   - EXECUTE is revoked from public/anon/authenticated below; only supabase_auth_admin may call it.
--   - STABLE (read-only) — Postgres forbids writes from within it.
create or replace function public.before_user_created_invite_gate(event jsonb)
returns jsonb
language plpgsql
stable
set search_path = public, pg_catalog
as $$
declare
    gate      public.signup_gate%rowtype;
    submitted text;
begin
    select * into gate from public.signup_gate where id = true;

    -- Fail OPEN when the gate is unconfigured or disabled. This is an invitation wall, not the auth
    -- boundary itself; a missing/disabled row must never lock everyone out of signup. The seed below
    -- guarantees a row, so "not found" is only an edge (e.g. a manual delete).
    if not found or not gate.enforced then
        return '{}'::jsonb;
    end if;

    submitted := coalesce(
        event #>> '{user,user_metadata,invite_code}',
        event #>> '{user,raw_user_meta_data,invite_code}'
    );

    if submitted is not null and submitted = gate.invite_code then
        return '{}'::jsonb;
    end if;

    return jsonb_build_object(
        'error',
        jsonb_build_object(
            'http_code', 403,
            'message', 'A valid invitation code is required to create an account.'
        )
    );
end;
$$;

-- The hook may be executed only by the auth system, never by end-user roles.
revoke execute on function public.before_user_created_invite_gate(jsonb) from public, anon, authenticated;
grant execute on function public.before_user_created_invite_gate(jsonb) to supabase_auth_admin;

-- Seed the singleton with an obvious placeholder, enforced on. The code is committed (and thus
-- public), so it is intentionally NOT a real-looking code: the owner signs up once with it (their
-- email is on LUNARIS_ADMIN_EMAILS → they become an admin) and then rotates it from the Invitations
-- screen. Until rotated, anyone reading this repo could sign up — rotate it immediately after the
-- first deploy. (A non-placeholder default would read as a "real" code and invite that mistake.)
insert into public.signup_gate (id, invite_code, enforced)
values (true, 'change-me-after-first-signup', true)
on conflict (id) do nothing;
