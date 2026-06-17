-- Database-level test for the signup invite-gate (migration 20260617140000_signup_invite_gate.sql).
--
-- The Before-User-Created hook is the actual signup enforcement, so it is verified where it runs —
-- in Postgres, as the `supabase_auth_admin` role GoTrue invokes it with. The application tests
-- (apps/api/tests/test_signup_gate_api.py) cover the admin API over the in-memory store; this covers
-- the SQL the hook + RLS posture enforce.
--
-- Run it against a database that already has the migration applied:
--   supabase db reset && psql "$DATABASE_URL" -f supabase/tests/signup_invite_gate_test.sql
-- It runs in a transaction and ROLLs BACK, so it leaves the gate row unchanged. Any failed
-- assertion RAISEs and aborts with a non-zero exit.

begin;

-- Pin a known code + enforced state for the assertions, independent of the migration's placeholder
-- seed. Runs as the connecting superuser (bypasses RLS); rolled back at the end.
update public.signup_gate set invite_code = 'LUNARIS-BETA', enforced = true where id;  -- singleton

-- The hook runs as supabase_auth_admin (granted execute + a read policy by the migration).
set local role supabase_auth_admin;

do $$
declare r jsonb;
begin
  -- Correct code → allow (empty object).
  r := public.before_user_created_invite_gate(
    '{"user":{"user_metadata":{"invite_code":"LUNARIS-BETA"}}}'::jsonb);
  if r <> '{}'::jsonb then raise exception 'correct code should ALLOW, got %', r; end if;

  -- Wrong code → reject with a 403 error object.
  r := public.before_user_created_invite_gate(
    '{"user":{"user_metadata":{"invite_code":"WRONG"}}}'::jsonb);
  if not (r ? 'error') or (r #>> '{error,http_code}') <> '403' then
    raise exception 'wrong code should REJECT 403, got %', r;
  end if;

  -- Missing / empty metadata → reject.
  r := public.before_user_created_invite_gate('{"user":{"user_metadata":{}}}'::jsonb);
  if not (r ? 'error') then raise exception 'missing code should REJECT, got %', r; end if;
  r := public.before_user_created_invite_gate('{"user":{}}'::jsonb);
  if not (r ? 'error') then raise exception 'empty user should REJECT, got %', r; end if;

  -- The raw_user_meta_data fallback path also matches.
  r := public.before_user_created_invite_gate(
    '{"user":{"raw_user_meta_data":{"invite_code":"LUNARIS-BETA"}}}'::jsonb);
  if r <> '{}'::jsonb then raise exception 'raw_user_meta_data fallback should ALLOW, got %', r; end if;

  raise notice 'ENFORCED: PASS';
end $$;

reset role;

-- Open the gate (the admin "Require invitation code" toggle off); rolled back at the end.
update public.signup_gate set enforced = false where id;

set local role supabase_auth_admin;
do $$
declare r jsonb;
begin
  r := public.before_user_created_invite_gate(
    '{"user":{"user_metadata":{"invite_code":"WRONG"}}}'::jsonb);
  if r <> '{}'::jsonb then raise exception 'disabled gate should ALLOW a wrong code, got %', r; end if;
  r := public.before_user_created_invite_gate('{"user":{}}'::jsonb);
  if r <> '{}'::jsonb then raise exception 'disabled gate should ALLOW no code, got %', r; end if;
  raise notice 'DISABLED (fail-open): PASS';
end $$;
reset role;

-- Lockdown: an end-user role can neither execute the hook nor read the gate table.
set local role authenticated;
do $$
begin
  begin
    perform public.before_user_created_invite_gate('{"user":{}}'::jsonb);
    raise exception 'authenticated should NOT be able to execute the hook';
  exception when insufficient_privilege then raise notice 'EXECUTE lockdown: PASS';
  end;
  begin
    perform 1 from public.signup_gate;
    raise exception 'authenticated should NOT be able to read signup_gate';
  exception when insufficient_privilege then raise notice 'TABLE lockdown: PASS';
  end;
end $$;
reset role;

-- anon (the SPA's pre-login role) must also be locked out of the table.
set local role anon;
do $$
begin
  begin
    perform 1 from public.signup_gate;
    raise exception 'anon should NOT be able to read signup_gate';
  exception when insufficient_privilege then raise notice 'ANON lockdown: PASS';
  end;
end $$;
reset role;

rollback;
