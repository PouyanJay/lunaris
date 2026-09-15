-- Private immutable compile inputs contain assessment answers: browser roles get no reads.
-- Revisions survive course edits. Deleting the source or owner purges its private copies;
-- resolver access is always rechecked against the current source before any cache use.
create table public.live_corpus_snapshots (
    owner_id uuid not null references auth.users(id) on delete cascade,
    course_id text not null references public.courses(id) on delete cascade,
    digest text not null check (digest ~ '^[a-f0-9]{64}$'),
    adapter_version text not null check (length(adapter_version) between 1 and 100),
    schema_version text not null check (length(schema_version) between 1 and 30),
    payload jsonb not null check (jsonb_typeof(payload) = 'object'),
    created_at timestamptz not null default now(),
    primary key (owner_id, course_id, digest, adapter_version, schema_version),
    check (payload->'source'->>'courseId' = course_id),
    check (payload->'source'->>'digest' = digest),
    check (payload->'source'->>'adapterVersion' = adapter_version),
    check (payload->>'schemaVersion' = schema_version)
);
alter table public.live_corpus_snapshots enable row level security;
revoke all on table public.live_corpus_snapshots from public, anon, authenticated, service_role;
grant select, insert, delete on public.live_corpus_snapshots to service_role;
-- No UPDATE grant: duplicate revision inserts use ON CONFLICT DO NOTHING, never overwrite.
create index live_corpus_snapshots_course_idx on public.live_corpus_snapshots(course_id);
