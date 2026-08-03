-- Generalize the cost ledger's rollup key: course_id -> (subject_type, subject_id).
--
-- Why now, on an append-only ledger: costs were keyed by `course_id` because a course was the only
-- thing in the system that could spend money. Lunaris Live's concept graphs spend too, and a graph
-- is not a course — different id space, different lifecycle, different purge. Course ids and graph
-- ids are minted from independent sequences, so nothing stops them colliding, and under a
-- single-column key that collision silently merges one product's spend into the other's total.
-- These are immutable financial rows: re-keying them later is a migration on data nobody may
-- rewrite, which is the expensive kind. So the key is generalized before Live records its first row.
--
-- EXPAND ONLY — this migration is deliberately additive.
--   CD pushes migrations BEFORE it deploys the new image (cd-prod.yml: "Push DB migrations" then
--   "Deploy Container App"), so for the length of a deploy the PREVIOUS release is still writing
--   `course_id` and reading it back. Renaming or dropping the column here would take cost recording
--   down for that window. Instead: add the new columns, backfill, and index them; the new code
--   writes BOTH columns; a later CONTRACT migration drops `course_id` and renames `course_costs`
--   to `subject_costs` once no old code is running.
--
-- Access posture is unchanged: RLS stays enabled, owner-read / server-write, and no grant or policy
-- is touched — the new columns are covered by the existing per-table policies, which key on
-- `user_id`. Adding a column does not widen what a policy admits.
--
-- To reverse: alter table ... drop column subject_type, subject_id; drop the two indexes.

-- ─── The ledger ──────────────────────────────────────────────────────────────
-- Defaulted rather than left null: every row that exists today is a course's, and a default keeps
-- the previous release's inserts (which name no subject_type) valid for the length of the deploy.
alter table public.cost_events
    add column if not exists subject_type text not null default 'course'
        check (subject_type in ('course', 'live_graph')),
    add column if not exists subject_id text
        check (subject_id is null or length(subject_id) between 1 and 100);

-- Backfill: every existing row is a course's spend, keyed by the id it already carries.
update public.cost_events set subject_id = course_id where subject_id is null;

-- ─── The rollup ──────────────────────────────────────────────────────────────
alter table public.course_costs
    add column if not exists subject_type text not null default 'course'
        check (subject_type in ('course', 'live_graph')),
    add column if not exists subject_id text
        check (subject_id is null or length(subject_id) between 1 and 100);

update public.course_costs set subject_id = course_id where subject_id is null;

-- The new read shape: one subject's whole ledger (drill-through + rollup recompute). Replaces
-- cost_events_course_idx, which the contract migration drops with the column it indexes.
create index if not exists cost_events_subject_idx
    on public.cost_events (subject_type, subject_id);

-- The rollup's upsert conflict target. UNIQUE (not the primary key) until the contract migration:
-- `course_id` is still the PK for as long as the previous release depends on it, and a subject can
-- only ever have one rollup row either way.
create unique index if not exists course_costs_subject_key
    on public.course_costs (subject_type, subject_id);
