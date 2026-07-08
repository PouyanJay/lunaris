"""Integration tests for learning-event emission — the Phase-2 progress endpoints write
``learning_events`` telemetry as a side effect (no separate client instrumentation).

Contract under test: ``started`` fires only when a lesson first becomes in_progress,
``completed`` only when it transitions to done, ``mastered`` only when an objective mark newly
flips a knowledge component to mastered — and every emission is best-effort (a telemetry outage
never fails the progress write). Hermetic: real ASGI app, real HS256 tokens, in-memory stores.
(X-Request-Id correlation on these endpoints is already pinned by test_progress_api.py — not
re-asserted here.)
"""

from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, auth_headers
from lunaris_api.activity import (
    ActivityStoreUnavailableError,
    InMemoryActivityStore,
    LearningEvent,
)
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import (
    get_activity_store,
    get_course_service,
    get_progress_store,
)
from lunaris_api.progress import InMemoryProgressStore
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.schema import (
    Course,
    KnowledgeComponent,
    Lesson,
    MerrillSegments,
    Module,
    Objective,
    PrerequisiteGraph,
    Segment,
)


class _StubCourseService:
    """Just enough of CourseService for title/mastery derivation: owner-scoped ``get``."""

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
    """Two modules / two KCs: kc-a is taught by two objectives (mastery needs both), kc-b by one.
    Three lessons so lesson labels carry course-wide positions."""
    return Course(
        id="course-1",
        topic="How HTTPS works",
        graph=PrerequisiteGraph(
            nodes=[
                KnowledgeComponent(
                    id="kc-a",
                    label="TLS fundamentals",
                    definition="What TLS is.",
                    difficulty=0.3,
                    bloom_ceiling="understand",
                ),
                KnowledgeComponent(
                    id="kc-b",
                    label="Certificates",
                    definition="What certificates prove.",
                    difficulty=0.5,
                    bloom_ceiling="understand",
                ),
            ]
        ),
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
                        statement="Distinguish port 443 from 80.",
                        bloom_level="remember",
                        kc="kc-a",
                    ),
                ],
                lessons=[
                    Lesson(id="m-1-l0", segments=_segments()),
                    Lesson(id="m-1-l1", segments=_segments()),
                ],
            ),
            Module(
                id="m-2",
                title="Certificates and trust",
                objectives=[
                    Objective(
                        statement="Explain what a certificate authority signs.",
                        bloom_level="understand",
                        kc="kc-b",
                    ),
                ],
                lessons=[Lesson(id="m-2-l0", segments=_segments())],
            ),
        ],
    )


def _build_client(
    tmp_path: Path,
    course_service: _StubCourseService,
    activity_store: object,
    progress_store: InMemoryProgressStore | None = None,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    # One store per client (not per request) — transition dedup needs the previous state to
    # survive across requests.
    store = progress_store if progress_store is not None else InMemoryProgressStore()
    app.dependency_overrides[get_progress_store] = lambda: store
    app.dependency_overrides[get_activity_store] = lambda: activity_store
    app.dependency_overrides[get_course_service] = lambda: course_service
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=JWT_SECRET,
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def activity_store() -> InMemoryActivityStore:
    return InMemoryActivityStore()


@pytest.fixture
async def client(
    tmp_path: Path, activity_store: InMemoryActivityStore
) -> AsyncIterator[httpx.AsyncClient]:
    service = _StubCourseService()
    service.seed(_https_course(), owner_id=USER_A)
    async with _build_client(tmp_path, service, activity_store) as http_client:
        yield http_client


async def _put_lesson(client: httpx.AsyncClient, lesson_id: str, state: str) -> httpx.Response:
    return await client.put(
        "/api/courses/course-1/progress/lesson",
        json={"lessonId": lesson_id, "state": state},
        headers=auth_headers(USER_A),
    )


async def _put_objective(client: httpx.AsyncClient, index: int, module_id: str = "m-1") -> None:
    response = await client.put(
        "/api/courses/course-1/progress/objective",
        json={"moduleId": module_id, "objectiveIndex": index, "understood": True},
        headers=auth_headers(USER_A),
    )
    assert response.status_code == 204


async def test_first_lesson_open_emits_started_with_titles(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Act — the reader's auto-in_progress on first open.
    response = await _put_lesson(client, "m-2-l0", "in_progress")

    # Assert — one started event, titled for the feed (course topic + course-wide lesson label).
    assert response.status_code == 204
    events = await activity_store.events(user_id=USER_A)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "started"
    assert event.course_id == "course-1"
    assert event.course_title == "How HTTPS works"
    assert event.lesson_id == "m-2-l0"
    assert event.lesson_title == "Lesson 3 · Certificates and trust"


async def test_reopening_a_lesson_emits_nothing(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Arrange — the lesson is already in progress.
    await _put_lesson(client, "m-1-l0", "in_progress")

    # Act — the reader re-marks in_progress on every open; telemetry must not spam.
    await _put_lesson(client, "m-1-l0", "in_progress")

    # Assert
    events = await activity_store.events(user_id=USER_A)
    assert [event.event_type for event in events] == ["started"]


async def test_completing_a_lesson_emits_completed_once(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Arrange
    await _put_lesson(client, "m-1-l0", "in_progress")

    # Act — completing transitions to done; re-completing is a no-op transition.
    await _put_lesson(client, "m-1-l0", "done")
    await _put_lesson(client, "m-1-l0", "done")

    # Assert — newest-first: completed then started, no duplicates.
    events = await activity_store.events(user_id=USER_A)
    assert [event.event_type for event in events] == ["completed", "started"]


async def test_mastering_a_kc_emits_mastered_with_label(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Act — kc-a is taught by two objectives: the first mark must NOT emit, the second must.
    await _put_objective(client, 0)
    halfway = await activity_store.events(user_id=USER_A)
    await _put_objective(client, 1)

    # Assert
    assert halfway == []
    events = await activity_store.events(user_id=USER_A)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "mastered"
    assert event.kc_id == "kc-a"
    assert event.kc_label == "TLS fundamentals"
    assert event.course_title == "How HTTPS works"


async def test_remarking_an_objective_does_not_remaster(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Arrange — kc-b mastered via its single objective.
    await _put_objective(client, 0, module_id="m-2")

    # Act — idempotent re-mark.
    await _put_objective(client, 0, module_id="m-2")

    # Assert — exactly one mastered event.
    events = await activity_store.events(user_id=USER_A)
    assert [event.event_type for event in events] == ["mastered"]


async def test_unmarking_an_objective_emits_nothing(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Arrange — kc-b mastered via its single objective.
    await _put_objective(client, 0, module_id="m-2")

    # Act — un-mark: history records what happened; it is never rewritten or extended by undo.
    response = await client.put(
        "/api/courses/course-1/progress/objective",
        json={"moduleId": "m-2", "objectiveIndex": 0, "understood": False},
        headers=auth_headers(USER_A),
    )

    # Assert — the original mastered event stands alone.
    assert response.status_code == 204
    events = await activity_store.events(user_id=USER_A)
    assert [event.event_type for event in events] == ["mastered"]


async def test_toggle_flapping_remasters_by_design(
    client: httpx.AsyncClient, activity_store: InMemoryActivityStore
) -> None:
    # Regression pin for requirements A8: events are an append-only historical record, so
    # mark → unmark → re-mark legitimately re-emits mastered (the concept WAS re-mastered).
    # A future refactor that tracks lifetime-ever-mastered would change accepted behavior.
    # Arrange / Act
    await _put_objective(client, 0, module_id="m-2")
    await client.put(
        "/api/courses/course-1/progress/objective",
        json={"moduleId": "m-2", "objectiveIndex": 0, "understood": False},
        headers=auth_headers(USER_A),
    )
    await _put_objective(client, 0, module_id="m-2")

    # Assert
    events = await activity_store.events(user_id=USER_A)
    assert [event.event_type for event in events] == ["mastered", "mastered"]


async def test_telemetry_outage_never_fails_the_progress_write(tmp_path: Path) -> None:
    # Arrange — an activity store whose writes fail like a Supabase outage.
    class _DownStore:
        async def record_event(self, *, user_id: str | None, event: LearningEvent) -> None:
            raise ActivityStoreUnavailableError("activity backend unavailable")

        async def record_minute(self, *, user_id: str | None, bucket_start: datetime) -> None:
            raise ActivityStoreUnavailableError("activity backend unavailable")

        async def events(self, *, user_id: str | None) -> list[LearningEvent]:
            raise ActivityStoreUnavailableError("activity backend unavailable")

        async def minutes(self, *, user_id: str | None) -> list[datetime]:
            raise ActivityStoreUnavailableError("activity backend unavailable")

    service = _StubCourseService()
    service.seed(_https_course(), owner_id=USER_A)
    async with _build_client(tmp_path, service, _DownStore()) as client:
        # Act — both progress writes with telemetry down.
        lesson = await _put_lesson(client, "m-1-l0", "in_progress")
        objective = await client.put(
            "/api/courses/course-1/progress/objective",
            json={"moduleId": "m-2", "objectiveIndex": 0, "understood": True},
            headers=auth_headers(USER_A),
        )

    # Assert — telemetry is best-effort: the progress writes still succeed.
    assert lesson.status_code == 204
    assert objective.status_code == 204


async def test_lesson_write_outage_is_a_recoverable_503(tmp_path: Path) -> None:
    # Arrange — a progress store whose lesson write fails like a Supabase outage.
    from lunaris_api.progress import ProgressStoreUnavailableError

    class _DownProgressStore(InMemoryProgressStore):
        async def set_lesson(self, **_kwargs: object) -> None:  # type: ignore[override]
            raise ProgressStoreUnavailableError("progress backend unavailable")

    service = _StubCourseService()
    service.seed(_https_course(), owner_id=USER_A)
    async with _build_client(
        tmp_path, service, InMemoryActivityStore(), progress_store=_DownProgressStore()
    ) as client:
        # Act
        response = await _put_lesson(client, "m-1-l0", "in_progress")

    # Assert — the write itself failing IS the user's problem: a recoverable 503, never a raw 500.
    assert response.status_code == 503
    assert response.json()["detail"] == "Progress is temporarily unavailable"


async def test_unknown_course_still_emits_untitled_lesson_events(
    tmp_path: Path,
) -> None:
    # Arrange — no course payload seeded (e.g. a course the store can't load right now).
    service = _StubCourseService()
    activity_store = InMemoryActivityStore()
    async with _build_client(tmp_path, service, activity_store) as client:
        # Act
        response = await _put_lesson(client, "m-1-l0", "in_progress")

    # Assert — the fact is still recorded; titles are honestly absent, never guessed.
    assert response.status_code == 204
    events = await activity_store.events(user_id=USER_A)
    assert len(events) == 1
    assert events[0].event_type == "started"
    assert events[0].course_title is None
    assert events[0].lesson_title is None
