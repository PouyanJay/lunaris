-- Lunaris Live, Phase 2c (T4) — first-turn material, kept one concept ahead of the learner.
--
-- Plan §6: per-node material is "generated on demand and prefetched one node ahead (a node takes
-- 10–20 minutes to learn and ~1 minute to generate, so the runtime is always ahead of the learner)".
-- This is where what was prefetched waits: the tutor's worked example, hint and practice prompts
-- for a concept's FIRST turn, written before the learner reaches it, read by the turn that does,
-- and deleted then (a second pass over a concept generates fresh).
--
-- Shape notes:
--  * One row per (learner, map, concept), like live_knowledge, and for the same reason: material is
--    written for one learner's map (the graph is per learner, C1 grows it per session), and the
--    read the loop does is "everything kept for this map" — a handful of rows at most.
--  * The payload is the LessonParts contract as JSON, camelCase, identical to what the wire carries,
--    so a stored part and a live part are the same shape to the layout composer.
--  * Durable rather than in-process (U3): a 30-minute session outlives a deploy and may be served by
--    more than one replica, and material prefetched by one process has to be there for the request
--    that consumes it, wherever that runs.
--  * No FK to live_graphs, for the reason live_knowledge has none: a map can be purged on its own,
--    and orphaned material is unreachable, not harmful.
--
-- user_id is nullable here, unlike live_knowledge: the auth-off single-user path keeps its material
-- in the in-process store (Supabase is not configured when auth is not), so in practice every row is
-- owned — but the store's contract admits an unowned scope, and the identity index below keeps an
-- unowned row from ever meaning "everybody's" (or from being written twice).
--
-- Access posture: RLS enabled, OWNER-READ / SERVER-WRITE. The loop writes via service_role;
-- `authenticated` gets SELECT and nothing else. A learner writing their own material could not
-- corrupt a belief (material never grades anything), but it would put words in the tutor's mouth,
-- and the write path is the server's regardless.
--
-- To reverse: DROP TABLE IF EXISTS public.live_materials;

create table if not exists public.live_materials (
    user_id    uuid references auth.users (id) on delete cascade,
    graph_id   text not null check (length(graph_id) between 1 and 100),
    node_id    text not null check (length(node_id) between 1 and 100),
    payload    jsonb not null,
    created_at timestamptz not null default now()
);

-- The identity: one row per (learner, map, concept). A NULL owner is ONE owner (the auth-off path),
-- not "any" — `nulls not distinct` (Postgres 15+) is what makes the upsert's on_conflict land on
-- the same row for it, instead of inserting a duplicate every time.
create unique index if not exists live_materials_identity
    on public.live_materials (user_id, graph_id, node_id) nulls not distinct;

alter table public.live_materials enable row level security;

-- Defense in depth: drop ALL default grants, then grant back only SELECT (the same posture as
-- live_knowledge). The loop writes through service_role.
revoke all on table public.live_materials from public, anon, authenticated;
grant select on public.live_materials to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy live_materials_select_own on public.live_materials
    for select to authenticated using ((select auth.uid()) = user_id);
