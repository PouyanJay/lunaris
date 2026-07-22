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
from lunaris_runtime.schema import Course, CourseStatus, ReviewGate, ReviewGateStatus


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


# --- Variant coverage (course-review-publish T4) ---


def _seed_course(
    course_dir: Path,
    *,
    status: CourseStatus,
    course_id: str,
    gates: list[ReviewGate] | None = None,
) -> Course:
    course = Course(id=course_id, topic="t", status=status, review_gates=gates or [])
    CourseStore(course_dir).save(course)
    return course


@pytest.mark.parametrize(
    "status",
    [
        CourseStatus.DIAGNOSING,
        CourseStatus.MAPPING,
        CourseStatus.SEQUENCING,
        CourseStatus.AUTHORING,
        CourseStatus.VERIFYING,
    ],
)
async def test_publishing_a_still_building_course_is_409(
    client: httpx.AsyncClient, tmp_path: Path, status: CourseStatus
) -> None:
    # Only a review-held course can be approved; a build in flight is a conflict, not a publish.
    _seed_course(tmp_path, status=status, course_id="building")

    response = await client.post("/api/courses/building/publish")

    assert response.status_code == 409
    assert response.headers["x-request-id"]
    # The store is untouched — a 409 never advances the status.
    assert CourseStore(tmp_path).load("building").status is status


async def test_publishing_an_already_published_course_is_idempotent(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    # Re-approving is a harmless no-op (e.g. a double-click, or a stale tab) — 200, still published.
    _seed_course(tmp_path, status=CourseStatus.PUBLISHED, course_id="pub")

    response = await client.post("/api/courses/pub/publish")

    assert response.status_code == 200
    assert response.json()["status"] == "published"


async def test_publish_preserves_the_recorded_gates_and_caveats(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    # Owner override records nothing away: the gate reasons — the caveats the learner keeps seeing —
    # survive the publish unchanged.
    gates = [
        ReviewGate(
            key="grounding",
            label="Grounding honesty",
            status=ReviewGateStatus.CAVEAT,
            detail="This course was not grounded in the real CLB 10 standard.",
        )
    ]
    _seed_course(tmp_path, status=CourseStatus.REVIEW, course_id="held", gates=gates)

    body = (await client.post("/api/courses/held/publish")).json()

    assert body["status"] == "published"
    assert body["reviewGates"][0]["detail"] == gates[0].detail
    assert CourseStore(tmp_path).load("held").review_gates == gates


async def test_publish_rejects_an_unsafe_id_as_not_found(client: httpx.AsyncClient) -> None:
    # An unsafe id can't name a stored course (the traversal guard) → not-found, never a 500.
    response = await client.post("/api/courses/bad!id/publish")

    assert response.status_code == 404
    assert response.headers["x-request-id"]
