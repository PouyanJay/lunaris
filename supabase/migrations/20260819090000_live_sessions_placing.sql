-- Let a Lunaris Live session be PLACING: opened on a topic whose map is still compiling (P2c T1).
--
-- Plan §6: the moment a topic arrives, the compile starts and the tutor opens a placement
-- conversation, so the learner never sees a progress bar. That session exists before its map does,
-- and it is neither `active` (nothing is being taught) nor `closed` (it has barely begun). It is a
-- status of its own, and the row's CHECK has to admit it — or the first topic-opened session in
-- production fails at the write with a constraint error nothing upstream can translate.
--
-- EXPAND ONLY, and safe in both deploy directions. CD pushes migrations BEFORE the new image, so
-- the previous release runs against this constraint for the length of a deploy: it only ever
-- writes `active` and `closed`, both of which stay admitted. Nothing already stored becomes
-- invalid, because a CHECK is only evaluated on write. The `status` column's DEFAULT stays
-- `active`: a session opened on a map is unchanged.
--
-- Access posture is UNCHANGED: no policy, grant or column is touched. A learner still cannot write
-- or edit a session (every turn goes through the API, which owns the loop's invariants), and a
-- placing session is the most sensitive of them all — it is the learner talking about themselves.
--
-- NOT VALID first, then validated separately, for the reason the cost-subject migration gives:
-- adding a CHECK outright takes ACCESS EXCLUSIVE for the length of its verification scan, which
-- would block the previous release's writes during the deploy window; NOT VALID takes the lock only
-- for the catalog change, and VALIDATE scans under ShareUpdateExclusive, which concurrent writes do
-- not wait on. Both existing values are unchanged, so nothing stored can fail the validation.
--
-- To reverse: drop the constraint and re-add it without 'placing' (only safe once no placing rows
-- exist, which is why the reverse is not automatic).

alter table public.live_sessions
    drop constraint if exists live_sessions_status_check;

alter table public.live_sessions
    add constraint live_sessions_status_check
        check (status in ('placing', 'active', 'closed')) not valid;

alter table public.live_sessions validate constraint live_sessions_status_check;
