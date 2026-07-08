-- Unified UI Phase 10: bookmarks — user-saved lessons, concepts, and sources.
--
-- One owner-scoped table (the learner_progress posture): a save is an idempotent upsert on the
-- natural key (user, kind, course, target); un-saving deletes by the same key. Unlike
-- learning_events this is USER-MANAGED data, so `authenticated` keeps the full CRUD grant —
-- constrained to its own rows by RLS.
--
-- Identity notes:
--  * target_id is a lesson id, a knowledge-component id, or a CITATION id for sources — claims
--    carry no server-side identity, so a source save keys on the citation and carries the claim
--    text as `snippet`; `lesson_id` (sources only) points back at the owning lesson for the
--    deep link.
--  * Display fields (course_title, title, concept_tier, trust_tier, credibility) are denormalized
--    at save time — the bookmarks screen renders without re-fetching courses and a saved card
--    survives a course rebuild. course_id carries no hard FK to public.courses (house precedent).
--  * `note` exists per the product plan; nothing writes it yet (a future notes UI).
--
-- Access posture: RLS enabled with owner-only policies for `authenticated`; the backend
-- service_role client (bypasses RLS) reads/writes on the caller's behalf with app-layer scoping.
-- The revoke includes authenticated's DEFAULT grant so TRUNCATE/REFERENCES/TRIGGER never leak
-- (TRUNCATE is not governed by RLS — the Phase-9 hardening).
--
-- To reverse: DROP TABLE IF EXISTS public.bookmarks;

create table if not exists public.bookmarks (
    id           bigint generated always as identity primary key,
    user_id      uuid not null references auth.users (id) on delete cascade,
    kind         text not null check (kind in ('lesson', 'concept', 'source')),
    course_id    text not null check (length(course_id) between 1 and 100),
    target_id    text not null check (length(target_id) between 1 and 300),
    course_title text check (length(course_title) between 1 and 300),
    title        text check (length(title) between 1 and 300),
    lesson_id    text check (length(lesson_id) between 1 and 200),
    snippet      text check (length(snippet) between 1 and 2000),
    concept_tier integer check (concept_tier between 1 and 5),
    trust_tier   text check (length(trust_tier) between 1 and 40),
    credibility  real check (credibility between 0 and 1),
    note         text check (length(note) between 1 and 2000),
    saved_at     timestamptz not null default now(),
    -- The toggle's natural key: re-saving upserts, never duplicates.
    unique (user_id, kind, course_id, target_id)
);

-- The one read shape: a user's saves newest-first.
create index if not exists bookmarks_user_saved_idx on public.bookmarks (user_id, saved_at desc);

-- RLS (BLOCKING): owner-scoped — the learner reads and manages their own saves.
alter table public.bookmarks enable row level security;

-- Defense in depth: drop ALL default grants (public, anon, and authenticated's defaults), then
-- grant back exactly the intended CRUD set. The identity sequence needs no grant — GENERATED
-- ALWAYS columns are filled server-side on insert.
revoke all on table public.bookmarks from public, anon, authenticated;
grant select, insert, update, delete on public.bookmarks to authenticated;

-- `(select auth.uid())` (not bare auth.uid()) so Postgres evaluates it once per query, not per row.
create policy bookmarks_select_own on public.bookmarks
    for select to authenticated using ((select auth.uid()) = user_id);
create policy bookmarks_insert_own on public.bookmarks
    for insert to authenticated
    with check (user_id is not null and (select auth.uid()) = user_id);
create policy bookmarks_update_own on public.bookmarks
    for update to authenticated
    using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy bookmarks_delete_own on public.bookmarks
    for delete to authenticated using ((select auth.uid()) = user_id);
