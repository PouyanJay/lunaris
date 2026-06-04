"""ingest_directory (the `make ingest` core, P6.1): walk a folder → extract → ingest, idempotent."""

from pathlib import Path

from lunaris_grounding import (
    CorpusIngestor,
    DocumentExtractor,
    InMemoryCorpusStore,
    StubEmbedder,
    ingest_directory,
)
from lunaris_runtime.schema import AcquisitionMode, TrustTier

_DIM = 64


def _ingestor(store: InMemoryCorpusStore) -> CorpusIngestor:
    return CorpusIngestor(StubEmbedder(dim=_DIM), store)


async def test_ingest_directory_extracts_supported_files_and_skips_others(tmp_path: Path) -> None:
    # Arrange — a folder with a .txt, a .md, and an unsupported binary.
    (tmp_path / "a.txt").write_text("Dijkstra relaxes edges.")
    (tmp_path / "b.md").write_text("# Notes\n\nMore grounding text.")
    (tmp_path / "c.bin").write_bytes(b"\x00\x01\x02")
    store = InMemoryCorpusStore()

    # Act
    summary = await ingest_directory(
        tmp_path, course_id="c1", ingestor=_ingestor(store), extractor=DocumentExtractor()
    )

    # Assert — the two text files ingest as VOUCHED/MANUAL sources; the binary is skipped.
    assert {name for name, _ in summary.ingested} == {"a.txt", "b.md"}
    assert "c.bin" in summary.skipped and len(summary.skipped) == 1
    sources = await store.list_sources_for_course("c1")
    assert len(sources) == 2
    assert all(s.trust_tier is TrustTier.VOUCHED for s in sources)
    assert all(s.acquisition_mode is AcquisitionMode.MANUAL for s in sources)


async def test_ingest_directory_is_idempotent(tmp_path: Path) -> None:
    # Arrange — one file, ingested twice.
    (tmp_path / "a.txt").write_text("Dijkstra relaxes edges.")
    store = InMemoryCorpusStore()

    # Act — re-running over the same folder must not duplicate the source (deterministic source id).
    await ingest_directory(
        tmp_path, course_id="c1", ingestor=_ingestor(store), extractor=DocumentExtractor()
    )
    await ingest_directory(
        tmp_path, course_id="c1", ingestor=_ingestor(store), extractor=DocumentExtractor()
    )

    # Assert
    assert len(await store.list_sources_for_course("c1")) == 1
