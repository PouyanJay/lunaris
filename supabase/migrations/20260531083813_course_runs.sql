-- P3 T2: the course-run history index for the agent-UI sidebar.
--
-- One row per build, keyed by course_id (the id GET /api/courses/{id} re-opens it with). The
-- backend records a row at run start and updates status + counts at finish. The whole path is
-- server-side and runs as service_role — there is no user/auth model in the MVP, so history is
-- single-tenant. `run_id` is the correlation id threaded through the structured logs.

-- Keyed by course_id (PK): the backend upserts on start, so a re-run of the same course_id
-- REPLACES its row — history is last-run-per-course, not a full audit trail (fine for the MVP
-- sidebar). `status` mirrors the RunStatus StrEnum; the CHECK keeps the DB honest if a future
-- caller bypasses the app layer.
create table if not exists public.course_runs (
    id            text primary key,           -- the course_id the sidebar re-opens with
    run_id        text not null,              -- correlation id (logs ↔ this row)
    topic         text not null,
    status        text not null check (status in ('running', 'completed', 'failed')),
    kc_count      integer not null default 0,
    module_count  integer not null default 0,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- The sidebar lists most-recent-first; index the sort key.
create index if not exists course_runs_created_at_idx
    on public.course_runs (created_at desc);

-- RLS (BLOCKING): enabled with NO policies. course_runs is server-only — every read/write goes
-- through the backend service-role client, which bypasses RLS. anon and authenticated therefore
-- get nothing, the intended posture for an internal single-tenant history index. Mirrors the
-- Stage-4b grounding_corpus pattern.
alter table public.course_runs enable row level security;

-- Defense in depth: Supabase grants table privileges to anon + authenticated by default, and
-- PostgreSQL grants to the PUBLIC pseudo-role. This table is service-role-only (service_role
-- bypasses both RLS and these grants), so revoke from all three — if RLS were ever toggled off by
-- mistake, the missing grants still deny everyone but service_role. Mirrors the grounding_corpus
-- function-level revoke (public + anon + authenticated).
revoke all on table public.course_runs from public, anon, authenticated;
