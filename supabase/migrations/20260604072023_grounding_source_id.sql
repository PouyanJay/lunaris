-- P6.1: source-level identity on the grounding corpus.
--
-- Manual ingest (and later auto-discovery) groups a source's chunks under one ``source_id`` so the
-- corpus can be listed + deleted as sources, not raw chunks. The column is nullable: pre-P6.1 and
-- agent-path chunks have none and are simply not surfaced as source-level rows.

alter table public.grounding_documents
    add column if not exists source_id text;

-- Indexed for source-level delete (delete ... where source_id = ?) and the per-source fold in list.
create index if not exists grounding_documents_source_id_idx
    on public.grounding_documents (source_id);

-- RLS stays enabled with NO policies (set by the corpus migration); ALTER/CREATE INDEX don't change
-- it. The corpus remains server-only — list/delete go through the backend service-role client.
