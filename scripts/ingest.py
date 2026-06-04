"""``make ingest`` — bulk-ingest a folder of documents into a course's grounding corpus (P6.1).

Composes the env-selected corpus store + embedder with the document extractor and walks a directory,
ingesting every supported file (PDF/DOCX/MD/TXT) as a VOUCHED source. Persists only with real
Supabase + Voyage creds; without them it ingests to an ephemeral in-memory store (a dry-run that
still reports what WOULD be ingested).

Usage:  uv run python scripts/ingest.py <directory> --course <course_id>
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from lunaris_grounding import (
    CorpusIngestor,
    DocumentExtractor,
    FolderIngestSummary,
    InMemoryCorpusStore,
    StubEmbedder,
    SupabaseCorpusStore,
    VoyageEmbedder,
    ingest_directory,
)


def _build_ingestor() -> tuple[CorpusIngestor, bool]:
    """The real Voyage + Supabase ingestor when keyed, else an ephemeral in-memory one (dry-run)."""
    keys = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "EMBEDDINGS_API_KEY")
    if all(os.getenv(key) for key in keys):
        return CorpusIngestor(VoyageEmbedder(), SupabaseCorpusStore()), True
    return CorpusIngestor(StubEmbedder(), InMemoryCorpusStore()), False


async def _run(directory: Path, course_id: str) -> int:
    if not await asyncio.to_thread(directory.is_dir):
        print(f"error: {directory} is not a directory", file=sys.stderr)
        return 2
    ingestor, durable = _build_ingestor()
    if not durable:
        print("warning: no Supabase/embeddings keys — ingesting to an EPHEMERAL in-memory store")
    summary = await ingest_directory(
        directory, course_id=course_id, ingestor=ingestor, extractor=DocumentExtractor()
    )
    return _report(summary)


def _report(summary: FolderIngestSummary) -> int:
    for name, chunks in summary.ingested:
        print(f"  + {name} ({chunks} chunk{'s' if chunks != 1 else ''})")
    for name in summary.skipped:
        print(f"  - {name} (skipped: unsupported or empty)")
    print(f"ingested {len(summary.ingested)} source(s), skipped {len(summary.skipped)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a folder of docs into a course corpus.")
    parser.add_argument("directory", type=Path, help="the folder of documents to ingest")
    parser.add_argument("--course", required=True, help="the course id to scope the sources to")
    args = parser.parse_args()
    return asyncio.run(_run(args.directory, args.course))


if __name__ == "__main__":
    raise SystemExit(main())
