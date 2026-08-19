-- Let a Lunaris Live belief carry its place on the review ladder and its next review day (P2c T6).
--
-- Plan §6: sessions end with a schedule the learner can see and the next session honours. At the
-- close, every concept graded this session gets a due date from a named-constant ladder keyed on
-- how it stands (a held concept climbs a rung, its interval growing from one day; a forming one is
-- due tomorrow from the bottom). The next session's director retrieves anything due before it
-- introduces new material. This is a review LADDER, not a forgetting curve: beliefs still do not
-- decay across sessions; the date is the only cross-session pull there is.
--
-- EXPAND ONLY: a default of zero and a nullable date, so every row written before this exists
-- reads as "never scheduled" (which is what it was), and the previous release, which writes
-- neither column, keeps working through the deploy window.
--
-- Access posture is UNCHANGED, and it matters here as it did for the claim: the table is
-- SELECT-only for a learner because the director gates on these rows. A learner who could set
-- their own review day could postpone every check indefinitely; the write path stays the server's.
--
-- To reverse: `alter table public.live_knowledge drop column review_stage, drop column due_at;`
-- (nothing else reads them).

-- The rung is bounded above as well as below: the ladder grows geometrically, so a runaway
-- writer (a loop that closes without teaching, an ungated harness) would otherwise carry a rung
-- past anything a date can hold. Seven rungs at x2.5 from a day is a review eight months out,
-- which is as far as a ladder for a tutoring product has any business reaching; the Python side
-- stops climbing at the same rung (`review_ladder.LAST_RUNG`), and the column is the backstop.
alter table public.live_knowledge
    add column if not exists review_stage integer not null default 0
        check (review_stage between 0 and 7),
    add column if not exists due_at timestamptz;
