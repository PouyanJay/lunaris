"""Integration tests for the course cover-image API surface (course-cover-images T0 — walking
skeleton).

Traverses the real layers end to end: HTTP → enqueue router → in-memory cover queue → the real
``CoverWorker`` loop over the stub pipeline → in-memory cover storage + the course store → HTTP
status router with a signed image URL. The stub pipeline stands in for the GPT Image 2 + Claude
loop (Phase 2), so this proves the wiring — queue/worker/storage/course-payload/API — before any
provider call exists. Owner scoping, dedup, and the auth boundary are asserted here too.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import (
    get_course_store,
    get_cover_job_queue,
    get_cover_storage,
)
from lunaris_covers import CoverWorker, StubCoverPipeline
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import (
    CoverArtifactPaths,
    InMemoryCoverJobQueue,
    InMemoryCoverStorage,
)
from lunaris_runtime.schema import Course, CoverJobStatus


class _FakeCourseStore:
    """An owner-scoped in-memory course store double — the enqueue endpoint's ownership check and
    the worker's ``Course.cover`` write both go through it (a course owned by another user reads as
    not-found, like the real Supabase store)."""

    def __init__(self) -> None:
        self._by_owner: dict[tuple[str | None, str], Course] = {}

    def save(self, course: Course, *, owner_id: str | None = None) -> None:
        self._by_owner[(owner_id, course.id)] = course

    def load(self, course_id: str, *, owner_id: str | None = None) -> Course:
        course = self._by_owner.get((owner_id, course_id))
        if course is None:
            raise FileNotFoundError(course_id)
        return course

    def delete(self, course_id: str, *, owner_id: str | None = None) -> bool:
        return self._by_owner.pop((owner_id, course_id), None) is not None


def _seeded_course_store() -> _FakeCourseStore:
    """A store holding course-1 (owned by USER_A) — the course tests request a cover for."""
    store = _FakeCourseStore()
    store.save(Course(id="course-1", topic="How HTTP works"), owner_id=USER_A)
    return store


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        config_path=tmp_path / "config.json",
        supabase_jwt_secret=JWT_SECRET,  # auth ON
    )


@pytest.fixture
def queue() -> InMemoryCoverJobQueue:
    return InMemoryCoverJobQueue()


@pytest.fixture
def storage() -> InMemoryCoverStorage:
    return InMemoryCoverStorage()


@pytest.fixture
def course_store() -> _FakeCourseStore:
    return _seeded_course_store()


@pytest.fixture
def worker(
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
) -> CoverWorker:
    """The real worker loop over the same doubles the app's DI overrides serve."""
    return CoverWorker(
        queue=queue,
        pipeline=StubCoverPipeline(),
        storage=storage,
        course_store=course_store,  # type: ignore[arg-type]
        worker_id="cover-worker-test",
    )


def _build_client(
    tmp_path: Path,
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    app.dependency_overrides[get_cover_job_queue] = lambda: queue
    app.dependency_overrides[get_cover_storage] = lambda: storage
    app.dependency_overrides[get_course_store] = lambda: course_store
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(
    tmp_path: Path,
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, queue, storage, course_store) as http_client:
        yield http_client


_ENQUEUE = "/api/courses/course-1/cover"


# ── the walking skeleton: enqueue → worker → ready, end to end ──────────────────────


async def test_walking_skeleton_cover_roundtrip(
    client: httpx.AsyncClient,
    worker: CoverWorker,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
) -> None:
    # Arrange / Act — enqueue a cover for the owned course.
    enqueue = await client.post(_ENQUEUE, headers=auth_headers(USER_A))

    # Assert — accepted, queued, and the request is correlatable (X-Request-Id on every response).
    assert enqueue.status_code == 202
    assert enqueue.headers.get("X-Request-Id")
    job_id = enqueue.json()["job"]["id"]
    assert enqueue.json()["job"]["status"] == CoverJobStatus.QUEUED.value

    # Act — the real worker drains exactly one job (stub produce → upload → attach → settle).
    assert await worker.run_once() is True

    # Assert — status is READY with a signed image URL and populated structural provenance.
    got = await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))
    assert got.status_code == 200
    assert got.headers.get("X-Request-Id")
    body = got.json()
    assert body["job"]["status"] == CoverJobStatus.READY.value
    assert body["imageUrl"]  # the reader displays this signed URL
    prov = body["provenance"]
    assert prov is not None
    assert prov["jobId"] == job_id
    assert prov["source"] == "stub" and prov["model"] == "stub"
    assert prov["stylePreset"] == "nocturne"

    # Assert (behaviour, not surface) — the image landed in storage as real PNG bytes, and the
    # cover was folded onto the course payload as course material.
    paths = CoverArtifactPaths.for_coordinates(USER_A, "course-1", job_id)
    assert storage.read(paths.image)[:8] == b"\x89PNG\r\n\x1a\n"
    course = course_store.load("course-1", owner_id=USER_A)
    assert course.cover is not None
    assert course.cover.status == CoverJobStatus.READY
    assert course.cover.job_id == job_id


# ── dedup: a second enqueue returns the in-flight job, never a duplicate ─────────────


async def test_second_enqueue_is_deduped(client: httpx.AsyncClient) -> None:
    first = await client.post(_ENQUEUE, headers=auth_headers(USER_A))
    second = await client.post(_ENQUEUE, headers=auth_headers(USER_A))
    assert first.status_code == second.status_code == 202
    assert first.json()["job"]["id"] == second.json()["job"]["id"]


# ── ownership + the auth boundary ───────────────────────────────────────────────────


async def test_enqueue_on_unowned_course_is_404(client: httpx.AsyncClient) -> None:
    # USER_B does not own course-1 → a not-found answer that never leaks its existence.
    resp = await client.post(_ENQUEUE, headers=auth_headers(USER_B))
    assert resp.status_code == 404


async def test_status_is_owner_scoped(client: httpx.AsyncClient, worker: CoverWorker) -> None:
    enqueue = await client.post(_ENQUEUE, headers=auth_headers(USER_A))
    job_id = enqueue.json()["job"]["id"]
    await worker.run_once()
    # USER_B cannot read USER_A's cover job — 404, not another tenant's status.
    assert (
        await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_B))
    ).status_code == 404


async def test_anonymous_callers_get_401(client: httpx.AsyncClient) -> None:
    assert (await client.post(_ENQUEUE)).status_code == 401
    assert (await client.get("/api/covers/j1")).status_code == 401
