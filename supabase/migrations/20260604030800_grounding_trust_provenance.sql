-- P6.0: source trust + provenance on the grounding corpus.
--
-- Each chunk now records WHERE its evidence came from and HOW trustworthy it is, so a citation can
-- be graded + audited rather than merely "supported". The fields are constructed where the source
-- is acquired and flow untouched to the reader. `course_id` scopes a chunk to one course; retrieval
-- filters on it so a different (even similar) topic's evidence can never bleed in.

alter table public.grounding_documents
    add column if not exists source_type      text,
    add column if not exists trust_tier       text,
    add column if not exists credibility      double precision,
    add column if not exists fetched_at       timestamptz,
    add column if not exists acquisition_mode text,
    add column if not exists course_id        text;

-- Enforces the per-course retrieval boundary; the match RPC filters on this column.
create index if not exists grounding_documents_course_id_idx
    on public.grounding_documents (course_id);

-- RLS stays enabled with NO policies (set by the corpus migration); ALTER TABLE does not change it.
-- The corpus remains server-only — every read/write goes through the backend service-role client.

-- The match RPC gains a course_filter and now returns the trust/provenance columns. The old 3-arg
-- signature is dropped first: adding a parameter would otherwise create a second overload and leave
-- PostgREST to disambiguate. The new signature keeps every filter defaulted, so the legacy callers
-- (kc_filter/course_filter omitted) still resolve to this one function.
drop function if exists public.match_grounding_documents(vector, int, text);

-- Cosine-similarity search. Returns similarity in [0, 1] (1 - cosine distance), highest first.
-- The returned columns are the reader-facing trust set; acquisition_mode and course_id are
-- deliberately NOT returned — they are internal audit/scope metadata, and course_id is already the
-- caller's own filter argument.
--
-- SECURITY NOTE: SECURITY INVOKER is intentional — the sole caller is the backend service-role
-- client, which bypasses RLS and holds implicit SELECT on public tables (Supabase default).
-- Non-service-role callers get zero rows (RLS enabled, no policies), never elevated access.
create or replace function public.match_grounding_documents(
    query_embedding vector(1024),
    match_count int default 5,
    kc_filter text default null,
    course_filter text default null
)
returns table (
    id text,
    kc_id text,
    content text,
    title text,
    url text,
    source_type text,
    trust_tier text,
    credibility double precision,
    fetched_at timestamptz,
    similarity double precision
)
language sql
stable
security invoker
-- Pinned so no other schema can be injected into name resolution. `vector` may install into either
-- public (bare `create extension`) or extensions (Supabase-managed) — both are listed so the cosine
-- operators resolve in either layout; the table itself is always in public.
set search_path = public, extensions
as $$
    select
        d.id,
        d.kc_id,
        d.content,
        d.title,
        d.url,
        d.source_type,
        d.trust_tier,
        d.credibility,
        d.fetched_at,
        1 - (d.embedding <=> query_embedding) as similarity
    from public.grounding_documents d
    where (kc_filter is null or d.kc_id = kc_filter)
      and (course_filter is null or d.course_id = course_filter)
    order by d.embedding <=> query_embedding
    limit match_count;
$$;

-- BLOCKING: PostgreSQL grants EXECUTE to PUBLIC by default, and Supabase grants it to anon +
-- authenticated independently. This function is service-role-only (service_role bypasses EXECUTE
-- checks), so revoke from all three and grant to no one. Revoke targets the NEW 4-arg signature.
revoke execute on function public.match_grounding_documents(vector, int, text, text) from public;
revoke execute on function public.match_grounding_documents(vector, int, text, text) from anon;
revoke execute on function public.match_grounding_documents(vector, int, text, text) from authenticated;
