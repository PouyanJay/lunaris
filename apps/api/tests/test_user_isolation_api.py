"""Integration tests for per-user isolation (Phase 2, T3-app) — the app-layer half of the RLS work.

Two authenticated users build courses through the real HTTP → service → store path; each must see
ONLY their own runs/events/courses. Hermetic by design (mirrors ``test_me_api``): each user mints an
HS256 token signed with the secret the API is configured with — exactly what Supabase Auth does —
so the real auth + ownership-scoping path runs with no live Supabase.

The build path persists via the service-role client (a background task can outlive a short-lived
JWT), so isolation here is enforced at the *app* layer: ``user_id`` is stamped on every write and
every read/delete is filtered by it. RLS (proven in the migration) is the second, DB-level belt for
any user-JWT client; this suite proves the app belt the service-role path relies on.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET as _JWT_SECRET
from _auth import USER_A as _USER_A
from _auth import USER_B as _USER_B
from _auth import auth_headers as _auth
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_course_service
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import InMemoryRunEventStore, InMemoryRunStore
from lunaris_runtime.schema import Course


class _InMemoryCourseStore:
    """An owner-scoping in-memory course store — the hermetic stand-in for the Supabase store.

    The file ``CourseStore`` is single-user (it ignores ``owner_id``), so it can't exercise course
    isolation; this test double scopes by owner exactly as ``SupabaseCourseStore`` does: ``save``
    stamps the owner, ``load``/``delete`` honor it (a mismatched owner is not-found). ``owner_id``
    None means unscoped (auth-off parity).
    """

    def __init__(self) -> None:
        self._courses: dict[str, Course] = {}
        self._owners: dict[str, str | None] = {}

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self._courses[course.id] = course
        self._owners[course.id] = owner_id

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        course = self._courses.get(course_id)
        if course is None or (owner_id is not None and self._owners.get(course_id) != owner_id):
            raise FileNotFoundError(course_id)
        return course

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        if course_id not in self._courses:
            return False
        if owner_id is not None and self._owners.get(course_id) != owner_id:
            return False
        del self._courses[course_id]
        del self._owners[course_id]
        return True


def _build_client(tmp_path: Path, jwt_secret: str | None) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    service = CourseService(
        _InMemoryCourseStore(),
        build_stub_orchestrator,
        InMemoryRunStore(),
        event_store=InMemoryRunEventStore(),
    )
    app.dependency_overrides[get_course_service] = lambda: service
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
    async with _build_client(tmp_path, _JWT_SECRET) as http_client:
        yield http_client


async def _build_as(client: httpx.AsyncClient, sub: str, topic: str) -> tuple[str, str]:
    """Build a course as ``sub`` and return its (course_id, run_id)."""
    response = await client.post("/api/courses", json={"topic": topic}, headers=_auth(sub))
    assert response.status_code == 201, response.text
    return response.json()["id"], response.headers["x-run-id"]


async def _build_via_stream(client: httpx.AsyncClient, sub: str, topic: str) -> str:
    """Build a course over the SSE stream as ``sub`` (recording a replay log) and return its run_id.

    ASGITransport buffers the whole streamed response, so awaiting the GET runs the build to
    completion — the event recorder flushes its log on the way out.
    """
    response = await client.get("/api/courses/stream", params={"topic": topic}, headers=_auth(sub))
    assert response.status_code == 200, response.text
    return response.headers["x-run-id"]


async def test_each_user_lists_only_their_own_runs(client: httpx.AsyncClient) -> None:
    # Arrange — two users each build a course.
    a_course, _ = await _build_as(client, _USER_A, "graphs for A")
    b_course, _ = await _build_as(client, _USER_B, "graphs for B")

    # Act
    a_runs = (await client.get("/api/runs", headers=_auth(_USER_A))).json()
    b_runs = (await client.get("/api/runs", headers=_auth(_USER_B))).json()

    # Assert — each user sees exactly their own run, never the other's.
    assert [run["id"] for run in a_runs] == [a_course]
    assert [run["id"] for run in b_runs] == [b_course]


async def test_user_cannot_open_another_users_course(client: httpx.AsyncClient) -> None:
    # Arrange — A builds a course.
    a_course, _ = await _build_as(client, _USER_A, "A's private course")

    # Act / Assert — B is denied (404, not 200), A still sees their own.
    assert (await client.get(f"/api/courses/{a_course}", headers=_auth(_USER_B))).status_code == 404
    assert (await client.get(f"/api/courses/{a_course}", headers=_auth(_USER_A))).status_code == 200


async def test_user_cannot_delete_another_users_course(client: httpx.AsyncClient) -> None:
    # Arrange — A builds a course.
    a_course, _ = await _build_as(client, _USER_A, "A's deletable course")

    # Act — B tries to delete it (a mutation path, distinct risk from the reads above).
    b_delete = await client.delete(f"/api/courses/{a_course}", headers=_auth(_USER_B))

    # Assert — B is denied (404, the owner-scoped delete found nothing); A's course survives.
    assert b_delete.status_code == 404
    assert (await client.get(f"/api/courses/{a_course}", headers=_auth(_USER_A))).status_code == 200


async def test_user_cannot_replay_another_users_run_events(client: httpx.AsyncClient) -> None:
    # Arrange — A builds a course via the streaming endpoint, which records a replayable event log
    # (the await-full POST path records only the run row, not the transcript).
    a_run = await _build_via_stream(client, _USER_A, "A's build log")

    # Act — B asks for A's run events.
    b_view = (await client.get(f"/api/runs/{a_run}/events", headers=_auth(_USER_B))).json()
    a_view = (await client.get(f"/api/runs/{a_run}/events", headers=_auth(_USER_A))).json()

    # Assert — B sees nothing; A sees their own transcript.
    assert b_view == []
    assert len(a_view) > 0


async def test_anonymous_requests_are_rejected_when_auth_is_configured(
    client: httpx.AsyncClient,
) -> None:
    # Act — no Authorization header against an auth-configured server.
    create = await client.post("/api/courses", json={"topic": "anon"})
    runs = await client.get("/api/runs")

    # Assert — user routes require a token (mirrors the frontend AuthGate, server-side).
    assert create.status_code == 401
    assert runs.status_code == 401


async def test_auth_off_keeps_routes_unscoped(tmp_path: Path) -> None:
    # Arrange — no JWT secret: auth is off, so routes stay open + unscoped (today's behavior).
    async with _build_client(tmp_path, None) as anon_client:
        course_id, _ = await _build_as_unauthed(anon_client, "open build")

        # Act — no token needed; the run is listed and the course opens.
        runs = (await anon_client.get("/api/runs")).json()
        course = await anon_client.get(f"/api/courses/{course_id}")

    # Assert
    assert [run["id"] for run in runs] == [course_id]
    assert course.status_code == 200


async def _build_as_unauthed(client: httpx.AsyncClient, topic: str) -> tuple[str, str]:
    """Build a course with no Authorization header and return its (course_id, run_id)."""
    response = await client.post("/api/courses", json={"topic": topic})
    assert response.status_code == 201, response.text
    return response.json()["id"], response.headers["x-run-id"]
