-- P6.2: the editable source-authority config — the spine + field packs + denylist (plan §4a).
--
-- Authority is a *prior, not a gate* (§4a): a row sets a domain's trust tier, which the credibility
-- scorer reads (cached per run) as the dominant signal in the §4b blend. A SPINE domain counts across
-- every topic, a PACK domain only for runs in its field, a DENYLIST domain is never ingested. Nothing
-- lives in code — the table is seeded here and edited at runtime via the Trusted-sources UI (T4).
--
-- This migration creates the table + a small representative seed (proves the read path); T1 seeds the
-- complete §4a spine + CS-ML/Medicine/Physics/Chemistry/Shared packs + denylist.
--
-- To reverse: DROP TABLE IF EXISTS public.source_authorities;

create table if not exists public.source_authorities (
    id          uuid primary key default gen_random_uuid(),
    domain      text not null,
    kind        text not null check (kind in ('spine', 'pack', 'denylist')),
    field       text check (field in ('cs_ml', 'medicine', 'physics', 'chemistry', 'shared')),
    tier        text not null check (tier in ('official', 'reputable', 'open', 'blocked', 'vouched')),
    -- Nullable; constrained to the SourceType vocabulary so a typo (e.g. 'databse') is rejected at
    -- insert rather than silently dropped at read time by the store's tolerant enum parse.
    source_type text check (
        source_type in (
            'peer_reviewed', 'preprint', 'official', 'database', 'docs', 'reference', 'web'
        )
    ),
    note        text,
    created_at  timestamptz not null default now(),
    -- One row per (domain, field). NULLS NOT DISTINCT (PG15+) so two global (field IS NULL) rows for
    -- the same domain collide rather than both inserting — makes the seed + management upsert idempotent.
    constraint source_authorities_domain_field_key unique nulls not distinct (domain, field)
);

-- A PACK is field-scoped by definition; spine/denylist are global. Mirrors the SourceAuthority model
-- invariant so a malformed row can't enter from raw SQL either.
alter table public.source_authorities
    add constraint source_authorities_pack_has_field
    check ((kind = 'pack') = (field is not null));

-- RLS (BLOCKING): enabled with NO policies. Like the grounding corpus, this config is server-only —
-- every read/write goes through the backend service-role client (which bypasses RLS). anon and
-- authenticated therefore get nothing, the intended posture for an internal trust config.
alter table public.source_authorities enable row level security;

-- Defense in depth (mirrors course_runs / run_events): Supabase grants table privileges to anon +
-- authenticated by default. RLS already denies them, but if RLS were ever toggled off by mistake the
-- missing grants still leave service_role the only role with access.
revoke all on table public.source_authorities from public, anon, authenticated;

-- Representative seed (T0): one spine, one field pack, one denylist entry — enough to prove the
-- scorer's table read. T1 inserts the full §4a set with the same on-conflict-do-nothing shape.
insert into public.source_authorities (domain, kind, field, tier, source_type) values
    ('en.wikipedia.org', 'spine', null, 'reputable', 'reference'),
    ('pubmed.ncbi.nlm.nih.gov', 'pack', 'medicine', 'official', 'database'),
    ('bit.ly', 'denylist', null, 'blocked', null)
on conflict on constraint source_authorities_domain_field_key do nothing;
