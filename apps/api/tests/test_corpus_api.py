"""P6.1 manual-ingest API: the walking skeleton — pasted text → gate → corpus → list/delete, all
course-scoped, over the real ASGI app with an in-memory corpus (no Supabase/embeddings key)."""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.corpus_service import CorpusService
from lunaris_api.dependencies import get_corpus_service
from lunaris_grounding import InMemoryCorpusStore, StubEmbedder
from lunaris_runtime.logging import clear_correlation


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        secrets_path=tmp_path / "secrets.json",
    )
    # A fresh in-memory corpus per test (isolated from the process singleton + other tests). The
    # pipeline="stub" above is for get_course_service (not under test); get_corpus_service is
    # overridden outright, so the Supabase/embeddings branch never runs here.
    service = CorpusService(InMemoryCorpusStore(), StubEmbedder())
    app.dependency_overrides[get_corpus_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _add(client: httpx.AsyncClient, course_id: str, title: str, text: str) -> httpx.Response:
    return await client.post(
        "/api/corpus/sources", json={"courseId": course_id, "title": title, "text": text}
    )


async def test_paste_text_source_is_ingested_and_correlated(client: httpx.AsyncClient) -> None:
    # Act
    add = await _add(client, "course-1", "Dijkstra notes", "Dijkstra relaxes edges.")

    # Assert — accepted, with a source id + at least one chunk.
    assert add.status_code == 201
    body = add.json()
    assert body["accepted"] is True
    assert body["chunks"] >= 1
    assert body["sourceId"]
    # A correlation id was bound + returned (the handler's bind_request_id) — it also threads
    # structlog contextvars onto the ingest log line. (Asserting the header, not the log: the
    # grounding logger is process-cached, so capture_logs can't reliably intercept it under random
    # test order; the X-Request-Id header is the client-facing correlation surface anyway.)
    assert re.fullmatch(r"[0-9a-f]{32}", add.headers["X-Request-Id"])


async def test_ingested_source_is_listed_as_a_vouched_manual_source(
    client: httpx.AsyncClient,
) -> None:
    # Arrange
    source_id = (
        await _add(client, "course-1", "Dijkstra notes", "Dijkstra relaxes edges.")
    ).json()["sourceId"]

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
    source_id = (await _add(client, "course-1", "A", "Some grounding text.")).json()["sourceId"]

    # Act
    deleted = await client.delete(f"/api/corpus/{source_id}")

    # Assert — 204 and the list goes empty.
    assert deleted.status_code == 204
    after = await client.get("/api/corpus", params={"courseId": "course-1"})
    assert after.json() == []


async def test_corpus_list_is_scoped_to_the_course(client: httpx.AsyncClient) -> None:
    # Arrange — one source under course-1.
    await _add(client, "course-1", "A", "Some grounding text.")

    # Act — a different course's list.
    other = await client.get("/api/corpus", params={"courseId": "course-2"})

    # Assert — per-course scoping: course-2 sees nothing.
    assert other.json() == []


async def test_whitespace_only_text_is_rejected_with_a_reason(client: httpx.AsyncClient) -> None:
    # Act — a non-empty-by-length but blank source.
    add = await _add(client, "course-1", "blank", "   ")

    # Assert — the gate declines it with the specific reason, and nothing is ingested.
    assert add.status_code == 201
    body = add.json()
    assert body["accepted"] is False
    assert body["reason"] == "empty source"
    listed = await client.get("/api/corpus", params={"courseId": "course-1"})
    assert listed.json() == []
