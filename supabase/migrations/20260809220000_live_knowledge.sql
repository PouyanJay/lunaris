-- Lunaris Live, Phase 2a — the learner model: what one learner is believed to know about one map.
--
-- The only thing in a session that outlives it. A second session on the same map opens knowing what
-- the first established, which is what makes "spaced retrieval" able to span more than one sitting
-- (plan §11: the model persists across sessions).
--
-- Shape notes:
--  * One row per CONCEPT, not one document per map — unlike live_sessions and live_graphs. The write
--    pattern decides it: a turn produces evidence about exactly one concept, so a per-concept upsert
--    touches one row where a document rewrite would rewrite the learner's whole history of the map
--    on every answer. It also makes P2b's mastery meters ("this concept, across sessions") a lookup.
--  * The natural key is (user_id, graph_id, node_id). node_id is graph-local — the compiler mints
--    ids per compile — so mastery of "a" on one map says nothing about "a" on another, and the
--    graph_id in the key is what keeps those apart.
--  * estimate is the belief AT last_evidence_turn, deliberately not the belief now. Now is a decay
--    applied at read time (`recall_of`). Storing the undecayed value is what makes the row stable:
--    a persisted number that changed meaning with every passing turn could not be compared with
--    itself between sessions.
--  * No FK to live_graphs: a graph can be purged independently, and orphaned beliefs are a better
--    outcome than a purge that fails. They are unreachable anyway once the map is gone.
--
-- user_id is part of the primary key, so it cannot be null here — unlike live_graphs/live_sessions,
-- where the auth-off single-user path leaves it null. That path keeps its beliefs in the in-process
-- store (Supabase is not configured when auth is not), so nothing is lost by requiring it, and
-- requiring it removes the "unowned row" class from a table that records what a person understands.
--
-- Access posture: RLS enabled, OWNER-READ / SERVER-WRITE, same as its siblings. The loop writes via
-- service_role; `authenticated` gets SELECT and nothing else, so a learner can see their own
-- progress (P2b renders it) but can never write a belief about themselves.
--
-- To reverse: DROP TABLE IF EXISTS public.live_knowledge;

create table if not exists public.live_knowledge (
    user_id            uuid not null references auth.users (id) on delete cascade,
    graph_id           text not null check (length(graph_id) between 1 and 100),
    node_id            text not null check (length(node_id) between 1 and 100),
    -- A probability. The director compares it against thresholds, so a value outside the range
    -- would silently disable a rule rather than fail loudly.
    estimate           double precision not null check (estimate between 0 and 1),
    evidence_count     integer not null default 0 check (evidence_count >= 0),
    last_evidence_turn integer not null default 0 check (last_evidence_turn >= 0),
    updated_at         timestamptz not null default now(),
    primary key (user_id, graph_id, node_id)
);

-- The read the loop actually does: every belief this learner holds about this map, once per turn.
-- Served by the primary key's leading columns, so no separate index is needed.

alter table public.live_knowledge enable row level security;

-- Defense in depth: drop ALL default grants (public, anon, and authenticated's defaults), then grant
-- back only SELECT. A learner writing their own mastery directly would be able to skip the entire
-- curriculum — the belief is only meaningful because the grader is the only thing that sets it.
revoke all on table public.live_knowledge from public, anon, authenticated;
grant select on public.live_knowledge to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy live_knowledge_select_own on public.live_knowledge
    for select to authenticated using ((select auth.uid()) = user_id);
