-- Phase 2 (T8): per-user non-secret runtime config (model selection).
--
-- Replaces the single-process, file-backed ConfigStore for the per-tenant settings: each user picks
-- the Claude models their own builds use (LUNARIS_MODEL_STRONG / LUNARIS_MODEL_WORKER). Stored as a
-- key→value row per user. UNLIKE provider_credentials these values are NOT secret — the owner reads
-- and edits them — so the access posture is owner-scoped RLS (like courses/course_runs), not the
-- server-only lockdown the credential table uses.
--
-- Access posture: RLS enabled with owner-only policies for `authenticated` ((select auth.uid()) =
-- user_id), plus CRUD grants. A Supabase client bound to a user's JWT reads/writes ONLY its own
-- rows; the backend service_role client (which bypasses RLS) reads a user's config at build time to
-- inject the chosen model. LangSmith tracing/project stay operator-only deploy-env config and are
-- intentionally NOT modelled here (process-start observability, not per-tenant).
--
-- Fresh table, no existing rows → the FK to auth.users is added from the start (ON DELETE CASCADE,
-- so deleting a user drops their config). Additive + deploy-safe.
--
-- To reverse: DROP TABLE IF EXISTS public.user_runtime_config;

create table if not exists public.user_runtime_config (
    user_id      uuid not null references auth.users (id) on delete cascade,
    -- Kept in lockstep with PER_USER_CONFIG in user_config_store.py; a typo is rejected here rather
    -- than silently stored. (LangSmith keys are deliberately excluded — operator-only config.)
    config_key   text not null check (config_key in ('modelStrong', 'modelWorker')),
    -- A model id is free-form text within a sane bound; the app re-validates the same cap.
    config_value text not null check (length(config_value) between 1 and 200),
    updated_at   timestamptz not null default now(),
    -- One value per key per user; the API upserts on this PK to change a model in place.
    primary key (user_id, config_key)
);

-- RLS (BLOCKING): owner-scoped, like courses — the value is non-secret and the owner manages it.
alter table public.user_runtime_config enable row level security;

-- Defense in depth: Supabase grants the full privilege set to anon + authenticated on every new
-- public table. anon has no policy here, so RLS already denies it, but revoking the grant removes the
-- foothold entirely — if a future migration ever added an anon policy or RLS were toggled off, anon
-- still couldn't touch the table. (authenticated keeps its grant; RLS constrains it to its own rows.)
revoke all on table public.user_runtime_config from public, anon;

-- RLS policies require the role to hold table privileges; state authenticated's explicitly so the
-- policy set is self-contained + auditable.
grant select, insert, update, delete on public.user_runtime_config to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy user_runtime_config_select_own on public.user_runtime_config
    for select to authenticated using ((select auth.uid()) = user_id);
create policy user_runtime_config_insert_own on public.user_runtime_config
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy user_runtime_config_update_own on public.user_runtime_config
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy user_runtime_config_delete_own on public.user_runtime_config
    for delete to authenticated using ((select auth.uid()) = user_id);
