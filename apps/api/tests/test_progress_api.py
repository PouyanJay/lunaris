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
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_course_service, get_progress_store
from lunaris_api.progress import InMemoryProgressStore
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.schema import Course, Lesson, MerrillSegments, Module, Objective, Segment

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")


def _build_client(
    jwt_secret: str | None, tmp_path: Path, course_service: "_StubCourseService | None" = None
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    # A fresh store per test client: the process-wide in-memory singleton would otherwise leak
    # marks across tests.
    store = InMemoryProgressStore()
    app.dependency_overrides[get_progress_store] = lambda: store
    if course_service is not None:
        app.dependency_overrides[get_course_service] = lambda: course_service
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
def course_service() -> "_StubCourseService":
    return _StubCourseService()


@pytest.fixture
async def client(
    tmp_path: Path, course_service: "_StubCourseService"
) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(JWT_SECRET, tmp_path, course_service) as http_client:
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


async def test_marking_an_objective_understood_persists_it(client: httpx.AsyncClient) -> None:
    # Act — mark module m-1's second objective understood.
    put = await client.put(
        "/api/courses/course-1/progress/objective",
        json={"moduleId": "m-1", "objectiveIndex": 1, "understood": True},
        headers=auth_headers(USER_A),
    )
    snapshot = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_A))

    # Assert
    assert put.status_code == 204
    marks = snapshot.json()["objectives"]
    assert len(marks) == 1
    assert marks[0]["moduleId"] == "m-1"
    assert marks[0]["objectiveIndex"] == 1
    assert marks[0]["understoodAt"]


async def test_unmarking_an_objective_removes_it(client: httpx.AsyncClient) -> None:
    # Arrange
    body = {"moduleId": "m-1", "objectiveIndex": 0, "understood": True}
    await client.put(
        "/api/courses/course-1/progress/objective", json=body, headers=auth_headers(USER_A)
    )

    # Act — un-mark (idempotent: un-marking twice is fine).
    for _ in range(2):
        response = await client.put(
            "/api/courses/course-1/progress/objective",
            json={**body, "understood": False},
            headers=auth_headers(USER_A),
        )
        assert response.status_code == 204

    # Assert
    snapshot = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_A))
    assert snapshot.json()["objectives"] == []


async def test_lesson_state_advances_and_overwrites(client: httpx.AsyncClient) -> None:
    # Act — first open marks in_progress; completing overwrites to done.
    for state in ("in_progress", "done"):
        response = await client.put(
            "/api/courses/course-1/progress/lesson",
            json={"lessonId": "m-1-l0", "state": state},
            headers=auth_headers(USER_A),
        )
        assert response.status_code == 204

    # Assert
    snapshot = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_A))
    lessons = snapshot.json()["lessons"]
    assert len(lessons) == 1
    assert lessons[0] == {
        "lessonId": "m-1-l0",
        "state": "done",
        "updatedAt": lessons[0]["updatedAt"],
    }


async def test_progress_is_isolated_per_user(client: httpx.AsyncClient) -> None:
    # Arrange — user A marks an objective and a lesson.
    await client.put(
        "/api/courses/course-1/progress/objective",
        json={"moduleId": "m-1", "objectiveIndex": 0, "understood": True},
        headers=auth_headers(USER_A),
    )
    await client.put(
        "/api/courses/course-1/progress/lesson",
        json={"lessonId": "m-1-l0", "state": "done"},
        headers=auth_headers(USER_A),
    )

    # Act — user B reads the same course.
    snapshot = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_B))

    # Assert — nothing of A's leaks to B.
    assert snapshot.json()["objectives"] == []
    assert snapshot.json()["lessons"] == []


async def test_progress_writes_require_auth(client: httpx.AsyncClient) -> None:
    # Act / Assert
    put_objective = await client.put(
        "/api/courses/course-1/progress/objective",
        json={"moduleId": "m-1", "objectiveIndex": 0, "understood": True},
    )
    put_lesson = await client.put(
        "/api/courses/course-1/progress/lesson",
        json={"lessonId": "m-1-l0", "state": "done"},
    )
    assert put_objective.status_code == 401
    assert put_lesson.status_code == 401


async def test_invalid_lesson_state_is_rejected(client: httpx.AsyncClient) -> None:
    # Act — a state outside the in_progress|done vocabulary.
    response = await client.put(
        "/api/courses/course-1/progress/lesson",
        json={"lessonId": "m-1-l0", "state": "mastered"},
        headers=auth_headers(USER_A),
    )

    # Assert
    assert response.status_code == 422


class _StubCourseService:
    """Just enough of CourseService for the rollup derivation: owner-scoped ``get``."""

    def __init__(self) -> None:
        self._courses: dict[tuple[str | None, str], Course] = {}

    def seed(self, course: Course, *, owner_id: str | None = None) -> None:
        self._courses[(owner_id, course.id)] = course

    def get(self, course_id: str, *, owner_id: str | None = None) -> Course | None:
        return self._courses.get((owner_id, course_id))


def _segments() -> MerrillSegments:
    return MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )


def _https_course() -> Course:
    """Two modules: three objectives over two KCs, two lessons — small but rollup-complete."""
    return Course(
        id="course-1",
        topic="How HTTPS works",
        modules=[
            Module(
                id="m-1",
                title="Fundamentals",
                objectives=[
                    Objective(
                        statement="Explain HTTPS as HTTP over TLS.",
                        bloom_level="understand",
                        kc="kc-a",
                    ),
                    Objective(
                        statement="Distinguish port 443 from 80.", bloom_level="remember", kc="kc-a"
                    ),
                ],
                lessons=[Lesson(id="m-1-l0", segments=_segments())],
            ),
            Module(
                id="m-2",
                title="Handshake",
                objectives=[
                    Objective(
                        statement="Sequence the TLS handshake.", bloom_level="analyze", kc="kc-b"
                    )
                ],
                lessons=[Lesson(id="m-2-l0", segments=_segments())],
            ),
        ],
    )


async def test_snapshot_derives_rollups_from_the_course(
    client: httpx.AsyncClient, course_service: _StubCourseService
) -> None:
    # Arrange — a stored course; the learner understood both kc-a objectives + finished lesson 1.
    course_service.seed(_https_course(), owner_id=USER_A)
    for index in (0, 1):
        await client.put(
            "/api/courses/course-1/progress/objective",
            json={"moduleId": "m-1", "objectiveIndex": index, "understood": True},
            headers=auth_headers(USER_A),
        )
    await client.put(
        "/api/courses/course-1/progress/lesson",
        json={"lessonId": "m-1-l0", "state": "done"},
        headers=auth_headers(USER_A),
    )

    # Act
    snapshot = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_A))

    # Assert — counts, percent (lessons done / total), and per-KC mastery (ALL of a KC's
    # objectives understood).
    body = snapshot.json()
    assert body["summary"] == {
        "understoodCount": 2,
        "objectiveTotal": 3,
        "lessonsDone": 1,
        "lessonTotal": 2,
        "percent": 50,
    }
    assert body["kcMastery"] == {"kc-a": True, "kc-b": False}


async def test_snapshot_without_a_stored_course_has_no_summary(
    client: httpx.AsyncClient,
) -> None:
    # Act — progress rows are independent of the course payload; no course → no rollups.
    snapshot = await client.get("/api/courses/ghost/progress", headers=auth_headers(USER_A))

    # Assert
    body = snapshot.json()
    assert body["summary"] is None
    assert body["kcMastery"] == {}


async def test_progress_works_unauthenticated_when_auth_is_off(tmp_path: Path) -> None:
    # Arrange — no JWT secret: the single-user offline posture (progress lives in memory).
    async with _build_client(None, tmp_path) as client:
        # Act
        put = await client.put(
            "/api/courses/course-1/progress/lesson",
            json={"lessonId": "m-1-l0", "state": "in_progress"},
        )
        snapshot = await client.get("/api/courses/course-1/progress")

    # Assert
    assert put.status_code == 204
    assert snapshot.status_code == 200
    lessons = snapshot.json()["lessons"]
    assert len(lessons) == 1
    assert lessons[0]["lessonId"] == "m-1-l0"


async def test_rollups_survive_a_course_with_no_lessons(
    client: httpx.AsyncClient, course_service: _StubCourseService
) -> None:
    # Arrange — a degenerate course: objectives but zero authored lessons (a legal state).
    course_service.seed(
        Course(
            id="course-1",
            topic="Lessonless",
            modules=[
                Module(
                    id="m-1",
                    title="Only objectives",
                    objectives=[
                        Objective(statement="Explain X.", bloom_level="understand", kc="kc-a")
                    ],
                    lessons=[],
                )
            ],
        ),
        owner_id=USER_A,
    )

    # Act
    snapshot = await client.get("/api/courses/course-1/progress", headers=auth_headers(USER_A))

    # Assert — the zero-lesson guard yields 0%, not a division error.
    assert snapshot.status_code == 200
    assert snapshot.json()["summary"] == {
        "understoodCount": 0,
        "objectiveTotal": 1,
        "lessonsDone": 0,
        "lessonTotal": 0,
        "percent": 0,
    }
