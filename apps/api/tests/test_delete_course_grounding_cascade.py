"""Full-purge course delete (course-delete T4): deleting a course cascades to its grounding corpus.
Traverses the real CourseService.delete_course → _purge_course_grounding path over the in-memory
corpus store, asserting EVERY chunk for the course goes — including agent-path chunks with no
source_id (which list_sources_for_course hides) — while other courses survive. The corpus is
course-scoped, not owner-scoped (grounding_documents is server-only; a course has one owner)."""

from pathlib import Path

from lunaris_agent import build_stub_orchestrator
from lunaris_api.service import CourseService
from lunaris_grounding import GroundingDocument, InMemoryCorpusStore
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore

_OWNER = "00000000-0000-0000-0000-00000000000a"


def _doc(doc_id: str, course_id: str, source_id: str | None) -> GroundingDocument:
    return GroundingDocument(
        id=doc_id,
        kc_id="k1",
        content="Dijkstra relaxes edges.",
        embedding=(0.1,),
        course_id=course_id,
        source_id=source_id,
    )


def _service(tmp_path: Path, corpus: InMemoryCorpusStore) -> CourseService:
    return CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        corpus_store=corpus,
    )


async def _chunk_count(corpus: InMemoryCorpusStore, course_id: str) -> int:
    # match() sees every chunk (unlike list_sources_for_course, which hides source_id=None), so it
    # proves the source-less agent-path chunk is purged too.
    return len(await corpus.match([0.1], k=100, min_score=0.0, course_id=course_id))


async def test_delete_course_purges_the_grounding_corpus(tmp_path: Path) -> None:
    # Arrange — c1 has a manual source chunk AND a source-less agent-path chunk; c2 has one.
    corpus = InMemoryCorpusStore()
    await corpus.upsert(
        [
            _doc("d1", "c1", "s1"),
            _doc("d2", "c1", None),
            _doc("d3", "c2", "s2"),
        ]
    )
    (tmp_path / "c1.json").write_text("{}")

    # Act
    await _service(tmp_path, corpus).delete_course("c1", owner_id=_OWNER)

    # Assert — every c1 chunk is gone (including the source-less one); c2 survives.
    assert await _chunk_count(corpus, "c1") == 0
    assert await corpus.list_sources_for_course("c1") == []
    assert await _chunk_count(corpus, "c2") == 1


async def test_grounding_purge_is_course_scoped_even_when_unowned(tmp_path: Path) -> None:
    # The corpus has no owner column, so a course purge is course-scoped: it runs even for an
    # auth-off (owner_id=None) delete, unlike the owner-scoped progress/bookmark/activity purges.
    corpus = InMemoryCorpusStore()
    await corpus.upsert([_doc("d1", "c1", "s1")])
    (tmp_path / "c1.json").write_text("{}")

    await _service(tmp_path, corpus).delete_course("c1")

    assert await _chunk_count(corpus, "c1") == 0
