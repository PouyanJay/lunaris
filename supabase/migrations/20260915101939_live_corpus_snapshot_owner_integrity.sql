-- Atomically require snapshots to belong to the same owner as their Studio source.
-- id is already unique, so this supporting index adds no new constraint on Studio data.
create unique index courses_corpus_owner_key on public.courses(id, user_id);
alter table public.live_corpus_snapshots
    drop constraint live_corpus_snapshots_course_id_fkey,
    add constraint live_corpus_snapshots_source_owner_fkey
        foreign key (course_id, owner_id) references public.courses(id, user_id)
        on delete cascade;
