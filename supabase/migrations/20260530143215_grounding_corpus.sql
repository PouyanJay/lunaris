-- Stage 4b: the grounding corpus for pgvector retrieval (D2).
--
-- Candidate sources are chunked + embedded (Voyage AI voyage-3.5, 1024 dims) and stored
-- here; a claim is grounded by embedding it and nearest-neighbouring this table via
-- match_grounding_documents. The whole path is server-side and runs as service_role.

create extension if not exists vector;

create table if not exists public.grounding_documents (
    id          text primary key,
    kc_id       text not null,
    content     text not null,
    title       text,
    url         text,
    run_id      text,
    embedding   vector(1024) not null,   -- voyage-3.5
    created_at  timestamptz not null default now()
);

create index if not exists grounding_documents_kc_id_idx
    on public.grounding_documents (kc_id);

-- Approximate-nearest-neighbour index for cosine distance.
create index if not exists grounding_documents_embedding_idx
    on public.grounding_documents using hnsw (embedding vector_cosine_ops);

-- RLS (BLOCKING): enabled with NO policies. The grounding corpus is server-only — every
-- read/write goes through the backend service-role client, which bypasses RLS. anon and
-- authenticated therefore get nothing, which is the intended posture for an internal corpus.
alter table public.grounding_documents enable row level security;

-- Cosine-similarity search. Returns similarity in [0, 1] (1 - cosine distance), highest first.
--
-- SECURITY NOTE: SECURITY INVOKER is intentional — the sole caller is the backend
-- service-role client, which bypasses RLS and holds implicit SELECT on public tables
-- (Supabase default). Non-service-role callers get zero rows (RLS enabled, no policies),
-- never elevated access. If ever ported off Supabase, add GRANT SELECT ... TO service_role.
create or replace function public.match_grounding_documents(
    query_embedding vector(1024),
    match_count int default 5,
    kc_filter text default null
)
returns table (
    id text,
    kc_id text,
    content text,
    title text,
    url text,
    similarity double precision
)
language sql
stable
security invoker
-- Pinned so no other schema can be injected into name resolution. `vector` may install into
-- either public (bare `create extension`) or extensions (Supabase-managed) — both are listed
-- so the cosine operators resolve in either layout; the table itself is always in public.
set search_path = public, extensions
as $$
    select
        d.id,
        d.kc_id,
        d.content,
        d.title,
        d.url,
        1 - (d.embedding <=> query_embedding) as similarity
    from public.grounding_documents d
    where kc_filter is null or d.kc_id = kc_filter
    order by d.embedding <=> query_embedding
    limit match_count;
$$;

-- BLOCKING: PostgreSQL grants EXECUTE to PUBLIC by default, and Supabase grants it to anon +
-- authenticated independently. This function is service-role-only (service_role bypasses
-- EXECUTE checks), so revoke from all three and grant to no one.
revoke execute on function public.match_grounding_documents(vector, int, text) from public;
revoke execute on function public.match_grounding_documents(vector, int, text) from anon;
revoke execute on function public.match_grounding_documents(vector, int, text) from authenticated;
