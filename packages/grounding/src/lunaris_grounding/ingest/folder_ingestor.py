"""Ingest a folder of documents into a course's grounding corpus — the ``make ingest`` path (P6.1).

The non-interactive sibling of the manual-ingest API (P6.1): walk a directory, extract each
supported file's text (``IDocumentExtractor``), and ingest it as a VOUCHED/MANUAL source. Each
source's id is a deterministic content fingerprint, so re-running over the same folder is
idempotent. Unsupported or empty files are skipped (best-effort), never fatal — one bad file
won't sink the batch.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog
from lunaris_runtime.schema import AcquisitionMode, TrustTier

from lunaris_grounding.ingest.document_extractor import IDocumentExtractor
from lunaris_grounding.ingest.ingestor import CorpusIngestor
from lunaris_grounding.ingest.source import CandidateSource

logger = structlog.get_logger()

# Manual/operator sources are general course evidence, not tied to one KC (the verifier searches the
# whole course corpus); this sentinel just satisfies the chunk key. Mirrors the API CorpusService.
_MANUAL_KC = "manual"


@dataclass(frozen=True)
class FolderIngestSummary:
    """What an ``ingest_directory`` run did: the (path, chunks) accepted + the skipped paths.

    A tightly-coupled sibling of ``ingest_directory`` (its return contract), so the two share a file
    per the one-export rule's exception. Frozen — a value object, not mutated after the run.
    """

    ingested: tuple[tuple[str, int], ...] = ()
    skipped: tuple[str, ...] = ()


async def ingest_directory(
    directory: Path,
    *,
    course_id: str,
    ingestor: CorpusIngestor,
    extractor: IDocumentExtractor,
) -> FolderIngestSummary:
    """Ingest every supported file under ``directory`` into ``course_id``'s corpus (recursive)."""
    fetched_at = datetime.now(UTC).isoformat()
    ingested: list[tuple[str, int]] = []
    skipped: list[str] = []
    # rglob/read are blocking — run them off the event loop.
    paths = await asyncio.to_thread(lambda: sorted(p for p in directory.rglob("*") if p.is_file()))
    for path in paths:
        name = str(path.relative_to(directory))  # disambiguates same-named files in sub-folders
        data = await asyncio.to_thread(path.read_bytes)
        extracted = await extractor.extract(filename=path.name, content_type=None, data=data)
        if extracted is None:
            skipped.append(name)
            continue
        source = CandidateSource(
            kc_id=_MANUAL_KC,
            text=extracted.text,
            title=extracted.title or path.stem,
            trust_tier=TrustTier.VOUCHED,
            acquisition_mode=AcquisitionMode.MANUAL,
            fetched_at=fetched_at,
            course_id=course_id,
            source_id=_fingerprint(course_id, extracted.text),
        )
        chunks = await ingestor.ingest([source])
        ingested.append((name, chunks))
    summary = FolderIngestSummary(ingested=tuple(ingested), skipped=tuple(skipped))
    logger.info(
        "folder_ingested",
        course_id=course_id,
        ingested=len(summary.ingested),
        skipped=len(summary.skipped),
    )
    return summary


def _fingerprint(course_id: str, text: str) -> str:
    """A deterministic per-source id (course + content) so re-ingesting a file is idempotent."""
    return hashlib.sha256(f"{course_id}|{text}".encode()).hexdigest()[:32]
