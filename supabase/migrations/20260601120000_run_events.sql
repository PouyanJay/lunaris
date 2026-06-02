-- build-timeline Phase B: the append-only build-event log for replayable build sessions.
--
-- One row per streamed event of a run — every coarse `progress` stage and fine-grained `agent`
-- transcript beat the live SSE emitted, captured in emission order so a finished (or still-building)
-- run can be re-rendered into the same BuildTimeline. Where `course_runs` is the one-row-per-build
-- index, this is the full transcript. The whole path is server-side and runs as service_role — the
-- same single-tenant posture as `course_runs`. `run_id` is the correlation id threaded through the
-- structured logs and the key the log is read by; `course_id` is the key it is purged with when the
-- course is deleted.
--
-- To reverse: DROP TABLE IF EXISTS public.run_events;
-- (Safe to drop — the log is a non-authoritative operational record; the live SSE stream is the
-- source of truth and a missing log simply yields the "no build record" replay state.)

create table if not exists public.run_events (
    id          uuid primary key default gen_random_uuid(),
    run_id      text not null,                       -- correlation id (logs ↔ these rows); read key
    course_id   text not null,                       -- the course the run built; purge key
    seq         integer not null,                    -- run-scoped emission order, gap-free from 0
    kind        text not null check (kind in ('progress', 'agent')),
    payload     jsonb not null,                      -- the original ProgressEvent / AgentEvent wire dict
    created_at  timestamptz not null default now()   -- ops only; replay orders by seq, not wall clock
);

-- Ordered replay reads (`... where run_id = $1 order by seq`) and the gap-free-seq integrity
-- contract in one unique index: a run never has two events at the same seq.
create unique index if not exists run_events_run_seq_idx
    on public.run_events (run_id, seq);

-- Purge-with-course scans by course_id (every run of a deleted course).
create index if not exists run_events_course_id_idx
    on public.run_events (course_id);

-- RLS (BLOCKING): enabled with NO policies. run_events is server-only — every read/write goes
-- through the backend service-role client, which bypasses RLS. anon and authenticated therefore get
-- nothing, the intended posture for an internal single-tenant transcript. Mirrors course_runs.
alter table public.run_events enable row level security;

-- Defense in depth: Supabase grants table privileges to anon + authenticated by default, and
-- PostgreSQL grants to the PUBLIC pseudo-role. This table is service-role-only (service_role bypasses
-- both RLS and these grants), so revoke from all three — if RLS were ever toggled off by mistake, the
-- missing grants still deny everyone but service_role. Mirrors the course_runs revoke.
revoke all on table public.run_events from public, anon, authenticated;
