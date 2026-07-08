"""Integration tests for the activity API — the learner's telemetry surface (streaks, study
minutes, concepts, feed) derived from ``learning_events`` + ``study_minutes`` rows.

Hermetic: mints real HS256 tokens (the same verification path production takes) and runs on the
in-memory activity store (no Supabase creds in tests). The DB layer — schema + RLS — is proven
separately in tests/db against the local stack.
"""

import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.activity import (
    ActivityStoreUnavailableError,
    InMemoryActivityStore,
    LearningEvent,
)
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_activity_store
from lunaris_runtime.logging import clear_correlation

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")


def _build_client(
    jwt_secret: str | None,
    tmp_path: Path,
    activity_store: object | None = None,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    # A fresh store per test client: the process-wide in-memory singleton would otherwise leak
    # events across tests.
    store = activity_store if activity_store is not None else InMemoryActivityStore()
    app.dependency_overrides[get_activity_store] = lambda: store
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
def store() -> InMemoryActivityStore:
    return InMemoryActivityStore()


@pytest.fixture
async def client(tmp_path: Path, store: InMemoryActivityStore) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(JWT_SECRET, tmp_path, store) as http_client:
        yield http_client


def _event(**overrides: object) -> LearningEvent:
    defaults: dict = {
        "event_type": "completed",
        "course_id": "course-1",
        "course_title": "How HTTPS works",
        "lesson_id": "m-1-l0",
        "lesson_title": "Certificates and authentication",
        "kc_id": None,
        "kc_label": None,
        "occurred_at": datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
    }
    return LearningEvent(**{**defaults, **overrides})


async def test_activity_starts_empty_for_a_fresh_user(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/activity", headers=auth_headers(USER_A))

    # Assert — a user with no history gets an honest all-zero snapshot, never invented numbers.
    assert response.status_code == 200
    body = response.json()
    assert body["stats"] == {
        "currentStreak": 0,
        "longestStreak": 0,
        "minutesThisWeek": 0,
        "conceptsThisWeek": 0,
    }
    assert body["heat"] == []
    assert body["week"] == []
    assert body["feed"] == []
    # Correlation: every activity request carries a request id for log triangulation.
    assert _REQUEST_ID.fullmatch(response.headers["X-Request-Id"])


async def test_activity_requires_auth_when_configured(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/activity")

    # Assert
    assert response.status_code == 401


async def test_feed_surfaces_recorded_events(
    client: httpx.AsyncClient, store: InMemoryActivityStore
) -> None:
    # Arrange — the walking-skeleton path: a row recorded in the store must traverse
    # store → API → wire shape untouched.
    await store.record_event(user_id=USER_A, event=_event())

    # Act
    response = await client.get("/api/activity", headers=auth_headers(USER_A))

    # Assert
    assert response.status_code == 200
    feed = response.json()["feed"]
    assert len(feed) == 1
    item = feed[0]
    assert item["eventType"] == "completed"
    assert item["courseId"] == "course-1"
    assert item["courseTitle"] == "How HTTPS works"
    assert item["lessonId"] == "m-1-l0"
    assert item["lessonTitle"] == "Certificates and authentication"
    assert item["occurredAt"]


async def test_activity_is_scoped_per_user(
    client: httpx.AsyncClient, store: InMemoryActivityStore
) -> None:
    # Arrange
    await store.record_event(user_id=USER_A, event=_event())

    # Act — another user reads their activity.
    response = await client.get("/api/activity", headers=auth_headers(USER_B))

    # Assert — user B never sees user A's history.
    assert response.status_code == 200
    assert response.json()["feed"] == []


async def test_activity_unavailable_backend_is_a_recoverable_503(tmp_path: Path) -> None:
    # Arrange — a store whose reads fail the way the Supabase store fails.
    class _DownStore:
        async def events(self, *, user_id: str | None) -> list[LearningEvent]:
            raise ActivityStoreUnavailableError("activity backend unavailable")

        async def minutes(self, *, user_id: str | None) -> list[datetime]:
            raise ActivityStoreUnavailableError("activity backend unavailable")

    async with _build_client(JWT_SECRET, tmp_path, _DownStore()) as client:
        # Act
        response = await client.get("/api/activity", headers=auth_headers(USER_A))

    # Assert — a recoverable 503 (kept inside the CORS middleware), never a raw 500.
    assert response.status_code == 503
    assert response.json()["detail"] == "Activity is temporarily unavailable"
