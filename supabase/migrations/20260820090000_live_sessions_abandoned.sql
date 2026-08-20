-- Let a Lunaris Live session be ABANDONED: the learner walked away from it, rather than the
-- director ending it (journey live-session-lifecycle, T3).
--
-- Until now a session had no way to stop. The director closed it when the clock ran out or when
-- there was nothing left worth teaching, and a learner who wanted to leave could only shut the tab,
-- which left the row `active` for ever holding a transcript nobody would come back to. The first
-- real browser session hit exactly that: the learner asked how to stop, and there was no verb to
-- answer with.
--
-- Its own value rather than `closed`, and this is the whole reason the migration exists. A session
-- that ended *well* (recap, mastery delta, review schedule) and one somebody walked out of are
-- different facts about a learner. Collapsed into one status, every count of "sessions finished"
-- would be a lie, and the schedule ladder would be asked to explain review dates for a session that
-- never produced any. `SessionStatus.CLOSED`'s own docstring has said "distinct from abandoned"
-- since Phase 2a; this is where that stops being an aspiration.
--
-- EXPAND ONLY, and safe in both deploy directions. CD pushes migrations BEFORE the new image, so
-- the previous release runs against this constraint for the length of a deploy: it writes only
-- `placing`, `warming`, `active` and `closed`, all of which stay admitted. Nothing already stored
-- becomes invalid, because a CHECK is only evaluated on write. The column DEFAULT stays `active`.
--
-- Rolling back the IMAGE while this constraint stands is also safe: the previous release cannot
-- write `abandoned`, and a row already holding it is only ever read (`Session` would reject the
-- value on parse, which surfaces as `SessionFormatError` — a row this build cannot read — rather
-- than as an outage). That is the same posture the placing/warming migration took.
--
-- Access posture is UNCHANGED: no policy, grant or column is touched. A learner still cannot write
-- or edit a session directly; abandoning one goes through the API like every other transition, so
-- the loop's invariants stay in one place.
--
-- NOT VALID first, then validated separately, for the reason the placing migration gives: adding a
-- CHECK outright takes ACCESS EXCLUSIVE for the length of its verification scan, which would block
-- the previous release's writes during the deploy window; NOT VALID takes the lock only for the
-- catalog change, and VALIDATE scans under ShareUpdateExclusive, which concurrent writes do not
-- wait on. Every existing value is unchanged, so nothing stored can fail the validation.
--
-- To reverse: drop the constraint and re-add it without 'abandoned' (only safe once no such rows
-- exist, which is why the reverse is not automatic).

alter table public.live_sessions
    drop constraint if exists live_sessions_status_check;

alter table public.live_sessions
    add constraint live_sessions_status_check
        check (status in ('placing', 'warming', 'active', 'closed', 'abandoned')) not valid;

alter table public.live_sessions validate constraint live_sessions_status_check;
