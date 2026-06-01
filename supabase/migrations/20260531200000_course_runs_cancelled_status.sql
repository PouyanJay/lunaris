-- Run cancellation: extend the course_runs status CHECK to allow 'cancelled' — a run explicitly
-- terminated mid-build, distinct from 'failed' (an error or a client disconnect). Mirrors the
-- RunStatus StrEnum gaining CANCELLED.
--
-- The original constraint is the inline column CHECK from 20260531083813, auto-named
-- `course_runs_status_check`. Drop + re-add with the widened value set. RLS posture is unchanged:
-- the table stays RLS-enabled with no policies (service-role-only); this migration touches only the
-- CHECK, adds no grants, and creates no policy.
-- To reverse: drop this constraint and re-add it with check (status in ('running','completed',
-- 'failed')) — only safe once no rows hold status 'cancelled'.
alter table public.course_runs drop constraint if exists course_runs_status_check;

alter table public.course_runs
    add constraint course_runs_status_check
    check (status in ('running', 'completed', 'failed', 'cancelled'));
