-- Let the cost ledger name a Lunaris Live SESSION as a subject.
--
-- A session spends on every turn — a tutor call and a grader call each time the learner answers —
-- and it is not a graph: different id space, different lifecycle, different purge (a graph outlives
-- every session run on it, and "what did this session cost" is a question a learner will ask about
-- one sitting rather than about a map). D2 generalized this key to `(subject_type, subject_id)`
-- precisely so a new spender would be an enum value rather than a migration on immutable rows; the
-- CHECK constraint is the one part of that which still has to be widened here.
--
-- EXPAND ONLY, and safe in both deploy directions. CD pushes migrations BEFORE the new image, so
-- the previous release runs against this constraint for the length of a deploy: it only ever writes
-- 'course' and 'live_graph', both of which stay admitted. Nothing already stored becomes invalid,
-- because a CHECK is only evaluated on write.
--
-- Access posture is UNCHANGED: no policy, grant or column is touched. Widening a CHECK does not
-- widen what a policy admits — these rows stay owner-read / server-write, which matters more here
-- than almost anywhere else in the schema because a user who could write one could invent spend
-- against somebody else's account.
--
-- To reverse: drop the new constraints and re-add them without 'live_session' (only safe once no
-- live_session rows exist, which is why the reverse is not automatic).

alter table public.cost_events
    drop constraint if exists cost_events_subject_type_check;

-- NOT VALID first, then validated separately: adding a CHECK outright takes ACCESS EXCLUSIVE for
-- the length of its verification scan, which would block the previous release's inserts during the
-- deploy window this file's header is about. NOT VALID takes the lock only for the catalog change;
-- VALIDATE CONSTRAINT then scans under ShareUpdateExclusive, which concurrent writes do not wait on.
-- Both admitted values are unchanged, so nothing already stored can fail the validation.
alter table public.cost_events
    add constraint cost_events_subject_type_check
        check (subject_type in ('course', 'live_graph', 'live_session')) not valid;

alter table public.cost_events validate constraint cost_events_subject_type_check;

alter table public.course_costs
    drop constraint if exists course_costs_subject_type_check;

alter table public.course_costs
    add constraint course_costs_subject_type_check
        check (subject_type in ('course', 'live_graph', 'live_session')) not valid;

alter table public.course_costs validate constraint course_costs_subject_type_check;
