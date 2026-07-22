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
from lunaris_api.corpus_service import CorpusService as CorpusIngestService
from lunaris_api.dependencies import get_authority_store, get_corpus_service, get_course_service
from lunaris_api.service import CourseService
from lunaris_grounding import InMemoryCorpusStore, InMemorySourceAuthorityStore, StubEmbedder
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
    # In-memory corpus + trust config (shared per app, like the prod singletons) so the corpus and
    # source-authority isolation tests run hermetically — no Supabase or embeddings key.
    corpus_service = CorpusIngestService(InMemoryCorpusStore(), StubEmbedder())
    app.dependency_overrides[get_corpus_service] = lambda: corpus_service
    authority_store = InMemorySourceAuthorityStore()
    app.dependency_overrides[get_authority_store] = lambda: authority_store
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


async def test_user_cannot_publish_another_users_course(client: httpx.AsyncClient) -> None:
    # Arrange — A builds a course (course-review-publish: publishing is owner-scoped too).
    a_course, _ = await _build_as(client, _USER_A, "A's publishable course")

    # Act — B tries to approve/publish it.
    b_publish = await client.post(f"/api/courses/{a_course}/publish", headers=_auth(_USER_B))

    # Assert — B is denied (404: the owner-scoped lookup found nothing to publish); A can (the stub
    # build already published it, so A's own approve is an idempotent 200).
    assert b_publish.status_code == 404
    a_publish = await client.post(f"/api/courses/{a_course}/publish", headers=_auth(_USER_A))
    assert a_publish.status_code == 200


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


async def _add_corpus_text(
    client: httpx.AsyncClient, sub: str, course_id: str, text: str
) -> httpx.Response:
    return await client.post(
        "/api/corpus/sources",
        json={"courseId": course_id, "kind": "text", "title": "notes", "text": text},
        headers=_auth(sub),
    )


async def test_user_cannot_write_to_another_users_corpus(client: httpx.AsyncClient) -> None:
    # Arrange — A owns a course.
    a_course, _ = await _build_as(client, _USER_A, "A's grounded course")

    # Act — B tries to plant a source in A's corpus (grounding-poisoning vector).
    b_add = await _add_corpus_text(client, _USER_B, a_course, "B's poisoned claim.")

    # Assert — denied as not-found; A's corpus stays empty.
    assert b_add.status_code == 404
    a_list = await client.get("/api/corpus", params={"courseId": a_course}, headers=_auth(_USER_A))
    assert a_list.json() == []


async def test_user_cannot_read_another_users_corpus(client: httpx.AsyncClient) -> None:
    # Arrange — A owns a course with one source.
    a_course, _ = await _build_as(client, _USER_A, "A's corpus to read")
    assert (await _add_corpus_text(client, _USER_A, a_course, "A's text.")).status_code == 201

    # Act / Assert — B can't list A's sources; A still can.
    b_list = await client.get("/api/corpus", params={"courseId": a_course}, headers=_auth(_USER_B))
    assert b_list.status_code == 404
    a_list = await client.get("/api/corpus", params={"courseId": a_course}, headers=_auth(_USER_A))
    assert len(a_list.json()) == 1


async def test_user_cannot_delete_another_users_corpus_source(client: httpx.AsyncClient) -> None:
    # Arrange — A owns a course with one source.
    a_course, _ = await _build_as(client, _USER_A, "A's corpus to keep")
    source_id = (await _add_corpus_text(client, _USER_A, a_course, "Keep me.")).json()["sourceId"]

    # Act — B tries to delete A's source.
    b_delete = await client.delete(
        f"/api/corpus/{source_id}", params={"courseId": a_course}, headers=_auth(_USER_B)
    )

    # Assert — denied; the source survives for A.
    assert b_delete.status_code == 404
    a_list = await client.get("/api/corpus", params={"courseId": a_course}, headers=_auth(_USER_A))
    assert [row["sourceId"] for row in a_list.json()] == [source_id]


async def test_anonymous_corpus_requests_are_rejected_when_auth_is_configured(
    client: httpx.AsyncClient,
) -> None:
    # Act — no Authorization header on each corpus surface.
    add = await client.post(
        "/api/corpus/sources", json={"courseId": "c1", "kind": "text", "title": "t", "text": "x"}
    )
    listed = await client.get("/api/corpus", params={"courseId": "c1"})
    deleted = await client.delete(f"/api/corpus/{'0' * 32}", params={"courseId": "c1"})

    # Assert — the corpus is a write path into a course's grounding; anonymous is rejected.
    assert add.status_code == 401
    assert listed.status_code == 401
    assert deleted.status_code == 401


async def test_anonymous_authority_requests_are_rejected_when_auth_is_configured(
    client: httpx.AsyncClient,
) -> None:
    # Act — no Authorization header on each trust-config surface.
    listed = await client.get("/api/source-authorities")
    upserted = await client.put(
        "/api/source-authorities",
        json={"domain": "example.org", "kind": "spine", "tier": "reputable"},
    )
    deleted = await client.delete("/api/source-authorities", params={"domain": "example.org"})

    # Assert — the trust config steers every build's credibility floor; anonymous is rejected.
    assert listed.status_code == 401
    assert upserted.status_code == 401
    assert deleted.status_code == 401


async def test_authenticated_user_can_manage_authorities(client: httpx.AsyncClient) -> None:
    # Act — a signed-in user lists + upserts (the auth gate must not break the authed flow).
    put = await client.put(
        "/api/source-authorities",
        json={"domain": "example.org", "kind": "spine", "tier": "reputable"},
        headers=_auth(_USER_A),
    )
    listed = await client.get("/api/source-authorities", headers=_auth(_USER_A))

    # Assert
    assert put.status_code == 200
    assert [row["domain"] for row in listed.json()] == ["example.org"]


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
