-- Phase 2 (BYOK): per-user, encrypted-at-rest provider keys.
--
-- Each tenant brings their own LLM/search/video keys (anthropic / voyage / search / youtube). The
-- API encrypts a key with an app-level AES-256-GCM cipher (master key from the secret manager, never
-- the DB) and stores ONLY the ciphertext here — the plaintext never touches Postgres. `last4` is the
-- one plaintext-derived field, kept for masked status display ("•••• 9abc") without decrypting.
--
-- Access posture (most-locked-down, mirrors the grounding/source_authorities tables): RLS ENABLED
-- with NO policies + all grants revoked, so the table is reachable ONLY through the backend
-- service-role client (which bypasses RLS). The SPA must never read keys directly — it sets them and
-- sees masked status via the authed API — so anon/authenticated get nothing. Even if RLS were ever
-- toggled off by mistake, the revoked grants leave service_role the only role with access, and the
-- stored values are AEAD ciphertext regardless.
--
-- To reverse: DROP TABLE IF EXISTS public.provider_credentials;

create table if not exists public.provider_credentials (
    -- ON DELETE CASCADE: deleting a user removes their stored keys (no orphaned secrets). This is a
    -- fresh table with no existing rows, so the FK to auth.users is added from the start (unlike the
    -- T3 user_id columns, where it was deferred to avoid backfilling legacy rows).
    user_id     uuid not null references auth.users (id) on delete cascade,
    -- Kept in lockstep with BYOK_PROVIDERS in credential_store_protocol.py; a typo is rejected here
    -- rather than silently stored.
    provider    text not null check (provider in ('anthropic', 'voyage', 'search', 'youtube')),
    -- base64(AES-256-GCM ciphertext+tag) and base64(96-bit nonce). Stored as text (not bytea) so the
    -- opaque AEAD output round-trips through PostgREST without bytea hex-encoding friction.
    ciphertext  text not null,
    nonce       text not null,
    -- The last 4 chars of the plaintext key (or null for a <4-char key), for masked status display
    -- ("•••• 9abc") without decrypting. Constrained so an app bug can't store a longer key fragment.
    last4       text check (last4 is null or length(last4) = 4),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    -- One credential per provider per user; the API upserts on this PK to rotate a key in place.
    primary key (user_id, provider)
);

-- RLS (BLOCKING): enabled with NO policies — server-only, like the grounding corpus + trust config.
alter table public.provider_credentials enable row level security;

-- FORCE so even the table owner / `postgres` superuser session goes through RLS (and, with no
-- policies, sees zero rows). Without this, a direct psql/`db query`/pg_cron path as the postgres role
-- (rolbypassrls) could read every row. service_role still bypasses RLS by role attribute (the backend
-- legitimately uses it) — FORCE only closes the postgres-superuser path, which is exactly the gap to
-- shut on a secrets table.
alter table public.provider_credentials force row level security;

-- Defense in depth: Supabase grants table privileges to anon + authenticated by default. RLS already
-- denies them, but revoking the grants leaves service_role the only role with access even if RLS were
-- ever disabled by mistake.
revoke all on table public.provider_credentials from public, anon, authenticated;
