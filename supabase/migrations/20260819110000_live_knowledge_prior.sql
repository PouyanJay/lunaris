-- Let a Lunaris Live belief carry the placement interview's claim about it (P2c T3).
--
-- Plan §6: the interview "seeds the learner model with priors". A prior is a CLAIM, never
-- evidence: it does not move `estimate` and it does not count as demonstrated. It changes two things
-- only — the director skips a claimed chain to its boundary and verifies the deepest claim there
-- (a graded retrieval) before building on it, and Tier 2 reads it as the band for a concept the
-- learner has shown nothing about. The first evidence clears it, so a row with evidence never
-- carries one.
--
-- EXPAND ONLY: a nullable column with no default, so every row written before this exists reads
-- as "no claim" (which is what it was) and the previous release, which never writes the column,
-- keeps working through the deploy window.
--
-- Access posture is UNCHANGED, and it matters more here than the size of the change suggests: the
-- table is SELECT-only for a learner precisely because the director gates progress on these rows.
-- A learner who could write a prior could not skip anything by it (the director checks every
-- claim before it credits it), but they could tilt Tier 2's band; the write path stays the server's.
--
-- To reverse: `alter table public.live_knowledge drop column prior;` (nothing else reads it).

alter table public.live_knowledge
    add column if not exists prior double precision
        check (prior is null or prior between 0 and 1);
