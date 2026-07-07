"""Integration tests for the learner-progress API — the per-user substrate (objective mastery +
lesson state) that Home/Overview/Map/Activity read from.

Hermetic: mints real HS256 tokens (the same verification path production takes) and runs on the
in-memory progress store (no Supabase creds in tests). The DB layer — schema + RLS — is proven
separately in tests/db against the local stack.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")


def _build_client(jwt_secret: str | None, tmp_path: Path) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
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


async def test_progress_starts_empty_for_a_fresh_course(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_A))

    # Assert — a course the user never touched has an empty, well-formed snapshot.
    assert response.status_code == 200
    body = response.json()
    assert body["courseId"] == "course-1"
    assert body["objectives"] == []
    assert body["lessons"] == []
    # Correlation: every progress request carries a request id for log triangulation.
    assert _REQUEST_ID.fullmatch(response.headers["X-Request-Id"])


async def test_progress_requires_auth_when_configured(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/courses/course-1/progress")

    # Assert
    assert response.status_code == 401
