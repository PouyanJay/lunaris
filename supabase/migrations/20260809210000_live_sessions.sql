-- Lunaris Live, Phase 2a — the session: a learner's run at a compiled concept graph.
--
-- One owner-scoped table holding the session's head. A session is MUTABLE and short-lived: every
-- turn rewrites the row, and the whole thing is bounded to 25-40 minutes (plan §6). It is persisted
-- rather than held on a connection because a reload must not be able to destroy 40 minutes of
-- accumulated context about one learner — the same lesson Phase 1 learned when a dropped stream
-- nearly cancelled a three-minute compile.
--
-- Identity and shape notes:
--  * id is text (the service mints a uuid4 hex), matching `live_graphs` and `courses`.
--  * graph_id is a real column, NOT an FK. A graph can be purged independently, and a dangling
--    session is a better outcome than a purge that fails or cascades away a learner's history.
--    It is indexed because "my sessions on this map" is the one cross-session read that exists.
--  * status and turn_count are lifted OUT of the payload: a resume needs to know whether a session
--    is still going and how far it got without parsing the transcript, and a jsonb probe per row for
--    a list view is cheap to get right now and expensive to retrofit.
--  * payload is the camelCase wire JSON — the same bytes the web consumes and the same shape the
--    in-memory store holds, so a session round-trips identically through either store.
--
-- One row per session with the turns inside the payload, rather than a turns table: a session is
-- always read whole, and nothing yet wants one turn without the rest. A turns table earns its place
-- when something does — appending a turn per row is the cheaper write, but only once the read
-- pattern justifies the join.
--
-- Access posture: RLS enabled, OWNER-READ / SERVER-WRITE, identical to live_graphs. The loop runs on
-- the backend service_role client (it bypasses RLS, because a turn can outlive the caller's JWT), so
-- isolation rides on the service stamping the right user_id; `authenticated` gets SELECT and nothing
-- else. The revoke includes authenticated's DEFAULT grants so TRUNCATE/REFERENCES/TRIGGER never leak
-- (TRUNCATE is not governed by RLS).
--
-- To reverse: DROP TABLE IF EXISTS public.live_sessions;

create table if not exists public.live_sessions (
    id         text primary key check (length(id) between 1 and 100),
    user_id    uuid references auth.users (id) on delete cascade,
    graph_id   text not null check (length(graph_id) between 1 and 100),
    status     text not null default 'active' check (status in ('active', 'closed')),
    turn_count integer not null default 0 check (turn_count >= 0),
    payload    jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- The two read shapes beyond by-id: a learner's own sessions newest first, and their sessions on
-- one map (which is how "carry on where you left off" will find them).
create index if not exists live_sessions_user_idx on public.live_sessions (user_id, updated_at desc);
create index if not exists live_sessions_graph_idx on public.live_sessions (user_id, graph_id);

-- RLS (BLOCKING): owner-read; the loop writes via service_role.
alter table public.live_sessions enable row level security;

-- Defense in depth: drop ALL default grants (public, anon, and authenticated's defaults), then grant
-- back only SELECT. No learner ever writes a session directly — every turn goes through the API,
-- which owns the loop invariants (monotonic seq, a move behind every turn) a raw insert would
-- bypass.
revoke all on table public.live_sessions from public, anon, authenticated;
grant select on public.live_sessions to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy live_sessions_select_own on public.live_sessions
    for select to authenticated using ((select auth.uid()) = user_id);
