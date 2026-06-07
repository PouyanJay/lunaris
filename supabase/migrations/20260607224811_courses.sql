-- Azure Phase 1: the durable course store.
--
-- Moves the finished Course off local files (.courses/<id>.json) into Postgres, so a stateless /
-- multi-replica API can serve any course from any replica and courses survive a restart. One row per
-- course, keyed by course_id; `payload` is the camelCase Course wire JSON (the exact bytes the file
-- store wrote — Course.model_dump_json(by_alias=True)). `status` is a denormalized copy for cheap
-- listing/filtering; the payload is authoritative.
--
-- Single-tenant for now (server-side, service_role) — there is no end-user auth model in Phase 1.
-- Phase 2 (multi-tenancy) adds a `user_id` column + per-user RLS policies; this table is shaped so
-- that is an additive change. Mirrors the course_runs pattern.
create table if not exists public.courses (
    id          text primary key,            -- the course_id (uuid4().hex) GET /api/courses/{id} re-opens
    payload     jsonb not null,              -- the camelCase Course (model_dump_json by_alias)
    status      text not null,               -- denormalized CourseStatus copy; payload is authoritative
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

-- The library/sidebar lists most-recent-first; index the sort key (parity with course_runs).
create index if not exists courses_created_at_idx
    on public.courses (created_at desc);

-- RLS (BLOCKING): enabled with NO policies. courses is server-only in Phase 1 — every read/write goes
-- through the backend service_role client, which bypasses RLS. anon + authenticated therefore get
-- nothing, the intended posture until Phase 2 introduces per-user policies. Mirrors course_runs.
alter table public.courses enable row level security;

-- Defense in depth: Supabase grants table privileges to anon + authenticated by default, and
-- PostgreSQL grants to the PUBLIC pseudo-role. This table is service_role-only (service_role bypasses
-- both RLS and these grants), so revoke from all three — if RLS were ever toggled off by mistake, the
-- missing grants still deny everyone but service_role. Mirrors course_runs.
revoke all on table public.courses from public, anon, authenticated;
