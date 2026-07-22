"""Integration tests for the course publish (review → published) transition.

They traverse the real HTTP → service → CourseStore path with the file store: a course is seeded in
``review``, then approved via ``POST /api/courses/{id}/publish`` (course-review-publish). Owner
override — publishing does not re-run the gates; the disclosed caveats stay on the course."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore
from lunaris_runtime.schema import Course, CourseStatus


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def _seed_review_course(course_dir: Path, course_id: str = "rev1") -> Course:
    course = Course(id=course_id, topic="Bayesian inference", status=CourseStatus.REVIEW)
    CourseStore(course_dir).save(course)
    return course


async def test_publish_flips_review_to_published(client: httpx.AsyncClient, tmp_path: Path) -> None:
    # Arrange — a built course held in review (a publish gate didn't pass).
    _seed_review_course(tmp_path)

    # Act — the owner approves it.
    response = await client.post("/api/courses/rev1/publish")

    # Assert — 200 with the now-published course, correlation id surfaced.
    assert response.status_code == 200
    assert response.json()["status"] == "published"
    assert response.headers["x-request-id"]
    # Persisted, not merely echoed: re-read the store.
    stored = CourseStore(tmp_path).load("rev1")
    assert stored.status is CourseStatus.PUBLISHED


async def test_publish_unknown_course_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/courses/ghost/publish")

    assert response.status_code == 404
    assert response.headers["x-request-id"]  # id rides the error path too
