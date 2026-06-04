"""P6.1 manual-ingest API: pasted text / uploaded file / URL → gate → corpus → list/delete, all
course-scoped, over the real ASGI app with an in-memory corpus (no Supabase/embeddings key)."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.corpus_service import CorpusService
from lunaris_api.dependencies import get_corpus_service
from lunaris_grounding import (
    ExtractedContent,
    IContentExtractor,
    InMemoryCorpusStore,
    StubEmbedder,
)
from lunaris_runtime.logging import clear_correlation


class _FakeContentExtractor:
    """A stub URL extractor (no network): returns a canned ExtractedContent, or None to model a
    fetch/extract failure."""

    def __init__(self, result: ExtractedContent | None) -> None:
        self._result = result

    async def extract(self, url: str) -> ExtractedContent | None:
        return self._result


def _corpus_app(tmp_path: Path, *, content_extractor: IContentExtractor | None = None) -> FastAPI:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        secrets_path=tmp_path / "secrets.json",
    )
    # A fresh in-memory corpus per app (isolated). The URL extractor is injectable so URL tests stay
    # offline; the real DocumentExtractor is used for file tests (it needs no network/key).
    service = CorpusService(
        InMemoryCorpusStore(), StubEmbedder(), content_extractor=content_extractor
    )
    app.dependency_overrides[get_corpus_service] = lambda: service
    return app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=_corpus_app(tmp_path))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _add_text(
    client: httpx.AsyncClient, course_id: str, title: str, text: str
) -> httpx.Response:
    return await client.post(
        "/api/corpus/sources",
        json={"courseId": course_id, "kind": "text", "title": title, "text": text},
    )


async def test_paste_text_source_is_ingested_and_correlated(client: httpx.AsyncClient) -> None:
    # Act
    add = await _add_text(client, "course-1", "Dijkstra notes", "Dijkstra relaxes edges.")

    # Assert — accepted, with a source id + at least one chunk, and a 32-hex correlation id.
    assert add.status_code == 201
    body = add.json()
    assert body["accepted"] is True
    assert body["chunks"] >= 1
    assert body["sourceId"]
    assert re.fullmatch(r"[0-9a-f]{32}", add.headers["X-Request-Id"])


async def test_ingested_source_is_listed_as_a_vouched_manual_source(
    client: httpx.AsyncClient,
) -> None:
    # Arrange
    source_id = (await _add_text(client, "course-1", "Dijkstra notes", "Relaxes edges.")).json()[
        "sourceId"
    ]

    # Act
    listed = await client.get("/api/corpus", params={"courseId": "course-1"})

    # Assert — one source row, VOUCHED + MANUAL, with its title + chunk count (camelCase wire).
    assert listed.status_code == 200
    [row] = listed.json()
    assert row["sourceId"] == source_id
    assert row["title"] == "Dijkstra notes"
    assert row["trustTier"] == "vouched"
    assert row["acquisitionMode"] == "manual"
    assert row["chunkCount"] >= 1


async def test_source_can_be_deleted(client: httpx.AsyncClient) -> None:
    # Arrange
    source_id = (await _add_text(client, "course-1", "A", "Some grounding text.")).json()[
        "sourceId"
    ]

    # Act
    deleted = await client.delete(f"/api/corpus/{source_id}")

    # Assert — 204 and the list goes empty.
    assert deleted.status_code == 204
    after = await client.get("/api/corpus", params={"courseId": "course-1"})
    assert after.json() == []


async def test_corpus_list_is_scoped_to_the_course(client: httpx.AsyncClient) -> None:
    # Arrange — one source under course-1.
    await _add_text(client, "course-1", "A", "Some grounding text.")

    # Act — a different course's list.
    other = await client.get("/api/corpus", params={"courseId": "course-2"})

    # Assert — per-course scoping: course-2 sees nothing.
    assert other.json() == []


async def test_re_adding_the_same_text_is_rejected_as_a_duplicate(
    client: httpx.AsyncClient,
) -> None:
    # Arrange — the source is added once.
    first = await _add_text(client, "course-1", "A", "Identical grounding text.")

    # Act — re-add the identical content.
    second = await _add_text(client, "course-1", "A again", "Identical grounding text.")

    # Assert — the gate dedups: same source id, second declined, and only ONE source is listed.
    assert first.json()["accepted"] is True
    assert second.json()["accepted"] is False
    assert second.json()["reason"] == "already in the corpus"
    assert second.json()["sourceId"] == first.json()["sourceId"]
    listed = await client.get("/api/corpus", params={"courseId": "course-1"})
    assert len(listed.json()) == 1


async def test_blank_text_is_rejected_by_the_schema(client: httpx.AsyncClient) -> None:
    # Act — a kind=text body with only whitespace is invalid at the boundary.
    add = await client.post(
        "/api/corpus/sources",
        json={"courseId": "course-1", "kind": "text", "title": "blank", "text": "   "},
    )

    # Assert — 422, nothing ingested.
    assert add.status_code == 422
    assert (await client.get("/api/corpus", params={"courseId": "course-1"})).json() == []


async def test_upload_text_file_is_extracted_and_ingested(client: httpx.AsyncClient) -> None:
    # Act — a .txt upload (the real DocumentExtractor decodes it).
    add = await client.post(
        "/api/corpus/sources/file",
        data={"courseId": "course-1"},
        files={"file": ("dijkstra.txt", b"Dijkstra relaxes edges to find paths.", "text/plain")},
    )

    # Assert — accepted; the file stem becomes the source title.
    assert add.status_code == 201
    assert add.json()["accepted"] is True
    [row] = (await client.get("/api/corpus", params={"courseId": "course-1"})).json()
    assert row["title"] == "dijkstra"
    assert row["trustTier"] == "vouched"


async def test_upload_unsupported_file_is_rejected(client: httpx.AsyncClient) -> None:
    # Act — an unknown binary type can't be extracted.
    add = await client.post(
        "/api/corpus/sources/file",
        data={"courseId": "course-1"},
        files={"file": ("image.bin", b"\x00\x01\x02\x03", "application/octet-stream")},
    )

    # Assert — declined with a reason, nothing ingested.
    assert add.status_code == 201
    assert add.json()["accepted"] is False
    assert add.json()["reason"] == "unsupported or empty file"


async def test_add_url_source_extracts_and_ingests(tmp_path: Path) -> None:
    # Arrange — a fake URL extractor (no network) returns clean text.
    extractor = _FakeContentExtractor(
        ExtractedContent(
            url="https://example.edu/dijkstra", text="Dijkstra relaxes edges.", title="Dijkstra"
        )
    )
    transport = httpx.ASGITransport(app=_corpus_app(tmp_path, content_extractor=extractor))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        add = await client.post(
            "/api/corpus/sources",
            json={"courseId": "course-1", "kind": "url", "url": "https://example.edu/dijkstra"},
        )

        # Assert — accepted, listed with its extracted title + the source URL.
        assert add.status_code == 201
        assert add.json()["accepted"] is True
        [row] = (await client.get("/api/corpus", params={"courseId": "course-1"})).json()
        assert row["title"] == "Dijkstra"
        assert row["url"] == "https://example.edu/dijkstra"


async def test_re_adding_the_same_url_is_rejected_as_a_duplicate(tmp_path: Path) -> None:
    # Arrange — a URL whose extraction succeeds; the gate keys dedup on the URL itself.
    extractor = _FakeContentExtractor(
        ExtractedContent(url="https://example.edu/x", text="Edges relax.", title="X")
    )
    transport = httpx.ASGITransport(app=_corpus_app(tmp_path, content_extractor=extractor))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        body = {"courseId": "course-1", "kind": "url", "url": "https://example.edu/x"}
        first = await client.post("/api/corpus/sources", json=body)

        # Act — submit the same URL again.
        second = await client.post("/api/corpus/sources", json=body)

        # Assert — deduped on the URL; only one source is listed.
        assert first.json()["accepted"] is True
        assert second.json()["accepted"] is False
        assert second.json()["reason"] == "already in the corpus"
        assert len((await client.get("/api/corpus", params={"courseId": "course-1"})).json()) == 1


async def test_oversized_upload_is_rejected(client: httpx.AsyncClient) -> None:
    # Act — a file over the 10 MB cap is declined before it's read into the corpus.
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    add = await client.post(
        "/api/corpus/sources/file",
        data={"courseId": "course-1"},
        files={"file": ("big.txt", oversized, "text/plain")},
    )

    # Assert
    assert add.status_code == 201
    assert add.json()["accepted"] is False
    assert add.json()["reason"] == "file too large"


async def test_add_url_source_that_cannot_be_extracted_is_rejected(tmp_path: Path) -> None:
    # Arrange — the extractor returns None (unreachable / no extractable text).
    transport = httpx.ASGITransport(
        app=_corpus_app(tmp_path, content_extractor=_FakeContentExtractor(None))
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        add = await client.post(
            "/api/corpus/sources",
            json={"courseId": "course-1", "kind": "url", "url": "https://nope.example/x"},
        )

        # Assert — declined with a reason, nothing ingested.
        assert add.status_code == 201
        assert add.json()["accepted"] is False
        assert add.json()["reason"] == "could not fetch or extract the URL"
        assert (await client.get("/api/corpus", params={"courseId": "course-1"})).json() == []


async def test_non_http_url_scheme_is_rejected_at_the_boundary(client: httpx.AsyncClient) -> None:
    # Act — a file:// URL must never reach the fetcher (SSRF/file-read vector).
    add = await client.post(
        "/api/corpus/sources",
        json={"courseId": "course-1", "kind": "url", "url": "file:///etc/passwd"},
    )

    # Assert — rejected by the schema (422), nothing fetched or ingested.
    assert add.status_code == 422


async def test_internal_ip_url_is_blocked_by_the_ssrf_guard(tmp_path: Path) -> None:
    # Arrange — a well-formed http URL to a link-local/metadata IP must be blocked before fetch. The
    # extractor would "succeed" if reached, so a rejection proves the guard runs first.
    extractor = _FakeContentExtractor(
        ExtractedContent(url="http://169.254.169.254/", text="secrets", title="x")
    )
    transport = httpx.ASGITransport(app=_corpus_app(tmp_path, content_extractor=extractor))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        add = await client.post(
            "/api/corpus/sources",
            json={"courseId": "course-1", "kind": "url", "url": "http://169.254.169.254/latest"},
        )

        # Assert — the SSRF guard declined it; nothing ingested.
        assert add.json()["accepted"] is False
        assert add.json()["reason"] == "that URL is not allowed"
        assert (await client.get("/api/corpus", params={"courseId": "course-1"})).json() == []
