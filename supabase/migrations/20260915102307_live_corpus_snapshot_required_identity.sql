-- SQL CHECK permits NULL: missing/null JSON identity must explicitly fail closed.
alter table public.live_corpus_snapshots
    drop constraint live_corpus_snapshots_check,
    drop constraint live_corpus_snapshots_check1,
    drop constraint live_corpus_snapshots_check2,
    drop constraint live_corpus_snapshots_check3,
    add constraint live_corpus_snapshots_course_identity_check
        check (((payload->'source'->>'courseId') = course_id) is true),
    add constraint live_corpus_snapshots_digest_identity_check
        check (((payload->'source'->>'digest') = digest) is true),
    add constraint live_corpus_snapshots_adapter_identity_check
        check (((payload->'source'->>'adapterVersion') = adapter_version) is true),
    add constraint live_corpus_snapshots_schema_identity_check
        check (((payload->>'schemaVersion') = schema_version) is true);

-- Rollback: drop the four *_identity_check constraints above and restore the four
-- equality checks from 20260915101642_live_corpus_snapshots.sql with their original
-- generated names (live_corpus_snapshots_check, check1, check2, check3). That restores
-- the earlier NULL-permitting behavior; no data transformation is required.
