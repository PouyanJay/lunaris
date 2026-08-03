-- Lunaris Live, Phase 1 — the concept graph: a topic's map of what has to be learned before what.
--
-- One owner-scoped table holding the graph's head. Unlike a Studio course, a Live graph is NOT an
-- immutable build artifact: a session sends the learner somewhere the compiled map does not go, so
-- the map GROWS at runtime (constraint C1). `version` is the head's monotonic version, bumped by
-- every extension, and `save` upserts on `id` rather than inserting a new row per compile.
--
-- Identity notes:
--  * id is text (the compile mints a uuid4 hex), matching the house precedent for `courses` — no
--    hard FK from anywhere, so a graph can be purged without dangling references.
--  * topic and version are lifted OUT of the payload into real columns: they are the only fields
--    ever filtered or ordered on (a learner's list of maps), and a jsonb probe per row for a list
--    view is the kind of thing that is cheap to get right now and expensive to retrofit.
--  * payload is the camelCase wire JSON — the same bytes the web consumes and the same shape the
--    in-memory store holds, so a graph round-trips identically through either store.
--
-- Access posture: RLS enabled, OWNER-READ / SERVER-WRITE. A compile runs on the backend service_role
-- client (it bypasses RLS, because a compile can outlive the caller's JWT), so isolation rides on
-- the service stamping the right user_id; `authenticated` gets SELECT and nothing else. The revoke
-- includes authenticated's DEFAULT grants so TRUNCATE/REFERENCES/TRIGGER never leak (TRUNCATE is
-- not governed by RLS).
--
-- To reverse: DROP TABLE IF EXISTS public.live_graphs;

create table if not exists public.live_graphs (
    id         text primary key check (length(id) between 1 and 100),
    user_id    uuid references auth.users (id) on delete cascade,
    topic      text not null check (length(topic) between 1 and 200),
    version    integer not null default 1 check (version >= 1),
    payload    jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- The one read shape beyond by-id: a learner's own maps, newest first.
create index if not exists live_graphs_user_idx on public.live_graphs (user_id, updated_at desc);

-- RLS (BLOCKING): owner-read; the compiler writes via service_role.
alter table public.live_graphs enable row level security;

-- Defense in depth: drop ALL default grants (public, anon, and authenticated's defaults), then
-- grant back only SELECT. No user ever writes a graph directly — compiling and extending both go
-- through the API, which owns the assembly invariants a raw insert would bypass.
revoke all on table public.live_graphs from public, anon, authenticated;
grant select on public.live_graphs to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy live_graphs_select_own on public.live_graphs
    for select to authenticated using ((select auth.uid()) = user_id);
