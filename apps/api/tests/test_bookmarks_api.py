"""Integration tests for the bookmarks API — user-saved lessons/concepts/sources (Unified UI
Phase 10). Save is an idempotent upsert on the natural key (user, kind, course, target); remove
deletes by the same key (the client never knows row ids).

Hermetic: mints real HS256 tokens (the same verification path production takes) and runs on the
in-memory bookmark store (no Supabase creds in tests). The DB layer — schema + RLS — is proven
separately in tests/db against the local stack.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.app import create_app
from lunaris_api.bookmarks import BookmarkStoreUnavailableError, InMemoryBookmarkStore
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_bookmark_store
from lunaris_runtime.logging import clear_correlation

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")


def _build_client(
    jwt_secret: str | None,
    tmp_path: Path,
    bookmark_store: object | None = None,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    # A fresh store per test client: the process-wide in-memory singleton would otherwise leak
    # saves across tests.
    store = bookmark_store if bookmark_store is not None else InMemoryBookmarkStore()
    app.dependency_overrides[get_bookmark_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=jwt_secret,
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(JWT_SECRET, tmp_path) as http_client:
        yield http_client


def _lesson_payload(**overrides: object) -> dict:
    payload: dict = {
        "kind": "lesson",
        "courseId": "course-1",
        "targetId": "m-1-l0",
        "courseTitle": "How HTTPS works",
        "title": "Lesson 1 · Fundamentals",
        "lessonId": "m-1-l0",
    }
    return {**payload, **overrides}


async def test_bookmarks_start_empty(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/bookmarks", headers=auth_headers(USER_A))

    # Assert — an untouched account has an empty, well-formed list.
    assert response.status_code == 200
    assert response.json() == []
    # Correlation: every bookmarks request carries a request id for log triangulation.
    assert _REQUEST_ID.fullmatch(response.headers["X-Request-Id"])


async def test_saving_a_lesson_bookmark_round_trips(client: httpx.AsyncClient) -> None:
    # Act — the walking-skeleton path: save in the API, read it back on the wire.
    put = await client.put("/api/bookmarks", json=_lesson_payload(), headers=auth_headers(USER_A))
    listed = await client.get("/api/bookmarks", headers=auth_headers(USER_A))

    # Assert
    assert put.status_code == 204
    (bookmark,) = listed.json()
    assert bookmark["kind"] == "lesson"
    assert bookmark["courseId"] == "course-1"
    assert bookmark["targetId"] == "m-1-l0"
    assert bookmark["courseTitle"] == "How HTTPS works"
    assert bookmark["title"] == "Lesson 1 · Fundamentals"
    assert bookmark["savedAt"]


async def test_saving_twice_keeps_one_bookmark(client: httpx.AsyncClient) -> None:
    # Act — the toggle re-fires on double-click; the natural key makes it idempotent.
    for _ in range(2):
        response = await client.put(
            "/api/bookmarks", json=_lesson_payload(), headers=auth_headers(USER_A)
        )
        assert response.status_code == 204

    # Assert
    listed = await client.get("/api/bookmarks", headers=auth_headers(USER_A))
    assert len(listed.json()) == 1


async def test_removing_a_bookmark_deletes_by_natural_key(client: httpx.AsyncClient) -> None:
    # Arrange
    await client.put("/api/bookmarks", json=_lesson_payload(), headers=auth_headers(USER_A))

    # Act — removing twice is fine (idempotent), like un-marking an objective.
    for _ in range(2):
        response = await client.delete(
            "/api/bookmarks",
            params={"kind": "lesson", "courseId": "course-1", "targetId": "m-1-l0"},
            headers=auth_headers(USER_A),
        )
        assert response.status_code == 204

    # Assert
    listed = await client.get("/api/bookmarks", headers=auth_headers(USER_A))
    assert listed.json() == []


async def test_bookmarks_are_scoped_per_user(client: httpx.AsyncClient) -> None:
    # Arrange
    await client.put("/api/bookmarks", json=_lesson_payload(), headers=auth_headers(USER_A))

    # Act / Assert — user B sees nothing of A's saves.
    listed = await client.get("/api/bookmarks", headers=auth_headers(USER_B))
    assert listed.json() == []


async def test_bookmarks_require_auth_when_configured(client: httpx.AsyncClient) -> None:
    # Act / Assert
    assert (await client.get("/api/bookmarks")).status_code == 401
    assert (await client.put("/api/bookmarks", json=_lesson_payload())).status_code == 401
    assert (
        await client.delete(
            "/api/bookmarks",
            params={"kind": "lesson", "courseId": "c", "targetId": "t"},
        )
    ).status_code == 401


async def test_source_bookmark_carries_trust_fields(client: httpx.AsyncClient) -> None:
    # Act — a source save keyed on the citation id, with the claim text as the snippet.
    put = await client.put(
        "/api/bookmarks",
        json={
            "kind": "source",
            "courseId": "course-1",
            "targetId": "cite-42",
            "courseTitle": "How HTTPS works",
            "title": "RFC 8446 — TLS 1.3",
            "lessonId": "m-1-l0",
            "snippet": "HTTPS encrypts data in transit.",
            "trustTier": "official",
            "credibility": 0.94,
        },
        headers=auth_headers(USER_A),
    )
    listed = await client.get("/api/bookmarks", headers=auth_headers(USER_A))

    # Assert
    assert put.status_code == 204
    (bookmark,) = listed.json()
    assert bookmark["trustTier"] == "official"
    assert bookmark["credibility"] == 0.94
    assert bookmark["snippet"] == "HTTPS encrypts data in transit."
    assert bookmark["lessonId"] == "m-1-l0"


async def test_unknown_kind_is_rejected(client: httpx.AsyncClient) -> None:
    # Act / Assert — the kind vocabulary mirrors the DB check.
    response = await client.put(
        "/api/bookmarks",
        json=_lesson_payload(kind="playlist"),
        headers=auth_headers(USER_A),
    )
    assert response.status_code == 422


async def test_unavailable_backend_is_a_recoverable_503(tmp_path: Path) -> None:
    # Arrange — a store that fails the way the Supabase store fails.
    class _DownStore:
        async def list(self, *, user_id: str | None) -> list:
            raise BookmarkStoreUnavailableError("bookmarks backend unavailable")

    async with _build_client(JWT_SECRET, tmp_path, _DownStore()) as client:
        # Act
        response = await client.get("/api/bookmarks", headers=auth_headers(USER_A))

    # Assert — recoverable 503, still correlated (the error path is where triangulation matters).
    assert response.status_code == 503
    assert response.json()["detail"] == "Bookmarks are temporarily unavailable"
    assert _REQUEST_ID.fullmatch(response.headers["X-Request-Id"])
