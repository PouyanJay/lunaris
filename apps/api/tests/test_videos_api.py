"""Integration tests for the explainer-video API surface (video V0-T3).

The surface: enqueue a lesson-video job, read its status, get signed playback URLs — all behind
the ``VIDEO_GENERATION_ENABLED`` operator flag (the prod kill-switch: OFF means the routes do not
exist, 404) and keyed-only (the Draft tier sees a clear feature-disabled refusal, 403). Traverses
the real layers (HTTP → router → queue/storage doubles); the worker's own loop is covered in
packages/video, and the live end-to-end spine lands in T5.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_run_event_store, get_video_job_queue, get_video_storage
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
)
from lunaris_video import StubVideoPipeline, VideoWorker


def _settings(tmp_path: Path, *, video_enabled: bool) -> Settings:
    return Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        config_path=tmp_path / "config.json",
        supabase_jwt_secret=JWT_SECRET,  # auth ON
        video_generation_enabled=video_enabled,
    )


@pytest.fixture
def queue() -> InMemoryVideoJobQueue:
    return InMemoryVideoJobQueue()


@pytest.fixture
def storage() -> InMemoryVideoStorage:
    return InMemoryVideoStorage()


@pytest.fixture
def events() -> InMemoryRunEventStore:
    return InMemoryRunEventStore()


@pytest.fixture
def worker(
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
) -> VideoWorker:
    """The real worker loop over the same doubles the app's DI overrides serve."""
    return VideoWorker(
        queue=queue,
        pipeline=StubVideoPipeline(),
        storage=storage,
        events=events,
        worker_id="worker-test",
    )


def _build_client(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    *,
    video_enabled: bool = True,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(
        tmp_path, video_enabled=video_enabled
    )
    app.dependency_overrides[get_video_job_queue] = lambda: queue
    app.dependency_overrides[get_video_storage] = lambda: storage
    app.dependency_overrides[get_run_event_store] = lambda: events
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def client(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # the caller is keyed
    async with _build_client(tmp_path, queue, storage, events) as http_client:
        yield http_client


_ENQUEUE = "/api/courses/course-1/lessons/lesson-1/video"


# ── the operator kill-switch ──────────────────────────────────────────────────────


async def test_flag_off_means_the_surface_does_not_exist(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — flag OFF (the prod posture until V7's rollout), caller fully keyed + authed.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    async with _build_client(tmp_path, queue, storage, events, video_enabled=False) as client:
        # Act / Assert — 404, not 403: a kill-switched feature is absent, not forbidden.
        assert (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).status_code == 404
        assert (await client.get("/api/videos/j1", headers=auth_headers(USER_A))).status_code == 404


# ── the auth boundary ─────────────────────────────────────────────────────────────


async def test_anonymous_callers_get_401(client: httpx.AsyncClient) -> None:
    # Act / Assert — both routes refuse an anonymous caller outright.
    assert (await client.post(_ENQUEUE)).status_code == 401
    assert (await client.get("/api/videos/j1")).status_code == 401


# ── the keyed-only tier gate ──────────────────────────────────────────────────────


async def test_keyless_caller_gets_a_feature_disabled_refusal(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — no vault, no env key: the Draft tier.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    async with _build_client(tmp_path, queue, storage, events) as client:
        # Act
        response = await client.post(_ENQUEUE, headers=auth_headers(USER_A))

        # Assert — a clear refusal naming the requirement, and nothing was enqueued.
        assert response.status_code == 403
        assert "key" in response.json()["detail"].lower()
        assert await queue.claim(worker_id="probe") is None


# ── enqueue + status read ─────────────────────────────────────────────────────────


async def test_enqueue_creates_an_owner_stamped_queued_job(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Act
    response = await client.post(_ENQUEUE, headers=auth_headers(USER_A))

    # Assert — 202 with the queued job's wire shape; the row is owner-stamped.
    assert response.status_code == 202
    body = response.json()
    job = body["job"]
    assert job["status"] == "queued"
    assert job["kind"] == "lesson"
    assert job["courseId"] == "course-1"
    assert job["lessonId"] == "lesson-1"
    assert job["userId"] == USER_A
    assert body["videoUrl"] is None
    stored = await queue.get(job_id=job["id"])
    assert stored is not None and stored.user_id == USER_A


async def test_status_read_is_owner_scoped(client: httpx.AsyncClient) -> None:
    # Arrange — A enqueues.
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]

    # Act / Assert — A reads their job; B gets a 404 (not a 403: existence is not leaked).
    assert (
        await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))
    ).status_code == 200
    assert (
        await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_B))
    ).status_code == 404
    assert (await client.get("/api/videos/ghost", headers=auth_headers(USER_A))).status_code == 404


async def test_a_ready_job_serves_signed_playback_urls(
    client: httpx.AsyncClient, worker: VideoWorker
) -> None:
    # Arrange — enqueue over HTTP, then the worker (the real loop, in-process) settles the job.
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True

    # Act
    response = await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))

    # Assert — ready, with playback URLs derived from the {user}/{course}/{job} convention.
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["status"] == "ready"
    assert f"{USER_A}/course-1/{job_id}/final.mp4" in body["videoUrl"]
    assert f"{USER_A}/course-1/{job_id}/poster.jpg" in body["posterUrl"]


# ── the lifespan worker (make run parity) ─────────────────────────────────────────


async def test_app_lifespan_runs_the_worker_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — env-driven app, the way `make run` boots it: flag ON, auth on, keyed, fast poll.
    # Fresh in-memory singletons so this test owns the queue the lifespan worker drains.
    from lunaris_api import dependencies

    monkeypatch.setattr(dependencies, "_in_memory_video_queue", InMemoryVideoJobQueue())
    monkeypatch.setattr(dependencies, "_in_memory_video_storage", InMemoryVideoStorage())
    monkeypatch.setenv("VIDEO_GENERATION_ENABLED", "true")
    monkeypatch.setenv("LUNARIS_VIDEO_WORKER_POLL_S", "0.01")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LUNARIS_PIPELINE", "stub")
    monkeypatch.setenv("LUNARIS_COURSE_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # Act — enqueue over HTTP; the lifespan-owned worker picks it up and settles it.
                job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"][
                    "id"
                ]

                async with asyncio.timeout(10):
                    while True:
                        body = (
                            await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))
                        ).json()
                        if body["job"]["status"] in {"ready", "failed"}:
                            break
                        await asyncio.sleep(0.01)

                # Assert — the walking skeleton, end-to-end through the running app.
                assert body["job"]["status"] == "ready"
                assert body["videoUrl"]
    finally:
        get_settings.cache_clear()


# ── variant coverage (V0-T5) ──────────────────────────────────────────────────────


async def test_both_routes_return_a_request_id_header(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Act
    enqueue = await client.post(_ENQUEUE, headers=auth_headers(USER_A))
    job_id = enqueue.json()["job"]["id"]
    status_read = await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))

    # Assert — every video request is traceable by its X-Request-Id, like the other routes.
    assert enqueue.headers["x-request-id"]
    assert status_read.headers["x-request-id"]
    assert enqueue.headers["x-request-id"] != status_read.headers["x-request-id"]


async def test_status_passes_through_the_wire_with_urls_only_when_ready(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue, worker: VideoWorker
) -> None:
    # Arrange — drive the job through every transition the V0 queue can reach.
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]

    async def read() -> dict:
        return (await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))).json()

    # Assert — queued: no URLs.
    body = await read()
    assert body["job"]["status"] == "queued"
    assert body["videoUrl"] is None and body["posterUrl"] is None

    # claimed → planning (in-flight): still no URLs.
    await queue.claim(worker_id="worker-test")
    body = await read()
    assert body["job"]["status"] == "planning"
    assert body["videoUrl"] is None and body["posterUrl"] is None

    # failed: terminal, no URLs, error carried on the wire.
    await queue.fail(job_id=job_id, error="video generation failed (RuntimeError)")
    body = await read()
    assert body["job"]["status"] == "failed"
    assert body["videoUrl"] is None
    assert "failed" in body["job"]["error"]

    # ready (after a real worker run on a fresh job): URLs present.
    job2 = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True
    body = (await client.get(f"/api/videos/{job2}", headers=auth_headers(USER_A))).json()
    assert body["job"]["status"] == "ready"
    assert body["videoUrl"] and body["posterUrl"]


async def test_the_job_id_correlates_api_queue_worker_and_event_log(
    client: httpx.AsyncClient,
    queue: InMemoryVideoJobQueue,
    events: InMemoryRunEventStore,
    worker: VideoWorker,
) -> None:
    # Act — enqueue over HTTP, settle with the real worker.
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True

    # Assert — ONE id triangulates every layer: the id the API handed the caller is the queue
    # row's id, the worker's run-scope, and the run_id the durable event log was written under
    # (owner-stamped). The structlog contextvars binding for the same id is proven directly in
    # packages/video/tests (capture_logs can't see cached loggers here).
    job = await queue.get(job_id=job_id)  # worker-level access: deliberately no owner filter
    assert job is not None and job.status.value == "ready"
    recorded = await events.list_for_run(run_id=job_id, owner_id=USER_A)
    assert recorded, "the worker left no event-log trail under the job's run_id"
    assert {event.payload.get("jobId") for event in recorded} == {job_id}
    assert recorded[-1].payload.get("status") == "ready"
