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
from lunaris_api.dependencies import (
    get_course_store,
    get_run_event_store,
    get_user_config_store,
    get_video_job_queue,
    get_video_storage,
)
from lunaris_api.user_config import InMemoryUserConfigStore
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import (
    InMemoryRunEventStore,
    InMemoryVideoJobQueue,
    InMemoryVideoStorage,
    VideoArtifactPaths,
)
from lunaris_runtime.schema import (
    Course,
    Lesson,
    MerrillSegments,
    Module,
    Segment,
    VideoJob,
    VideoKind,
    VideoProvenance,
)
from lunaris_runtime.video_build import lesson_video_input_hash
from lunaris_video import StubVideoPipeline, VideoWorker
from lunaris_video.schemas import BeatTiming, SceneTiming, TimingManifest


class _FakeCourseStore:
    """An owner-scoped in-memory course store double — enough for the enqueue endpoint's ownership
    check (a course owned by another user reads as not-found, like the real Supabase store)."""

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


def _seeded_lesson() -> Lesson:
    """The lesson the seeded store holds (course-1 / lesson-1). The single source so the staleness
    tests can recompute the exact input hash the GET will — a divergence would falsely read stale.
    """
    segments = MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )
    return Lesson(id="lesson-1", segments=segments)


def _seeded_course_store() -> _FakeCourseStore:
    """A store holding course-1 (owned by USER_A) with lesson-1 — the coordinates tests enqueue."""
    store = _FakeCourseStore()
    course = Course(
        id="course-1",
        topic="Algorithms",
        modules=[Module(id="m1", title="Sorting", lessons=[_seeded_lesson()])],
    )
    store.save(course, owner_id=USER_A)
    return store


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
    course_store: _FakeCourseStore | None = None,
    user_config_store: InMemoryUserConfigStore | None = None,
) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(
        tmp_path, video_enabled=video_enabled
    )
    app.dependency_overrides[get_video_job_queue] = lambda: queue
    app.dependency_overrides[get_video_storage] = lambda: storage
    app.dependency_overrides[get_run_event_store] = lambda: events
    app.dependency_overrides[get_course_store] = lambda: course_store or _seeded_course_store()
    if user_config_store is not None:
        app.dependency_overrides[get_user_config_store] = lambda: user_config_store
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


# ── the per-user master toggle (V6) ───────────────────────────────────────────────


async def test_master_toggle_off_refuses_on_demand_enqueue(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — keyed + authed, but the caller turned video OFF in Settings (V6 master toggle).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_config = InMemoryUserConfigStore()
    await user_config.set(user_id=USER_A, key="videoEnabled", value="false")
    async with _build_client(
        tmp_path, queue, storage, events, user_config_store=user_config
    ) as client:
        # Act
        response = await client.post(_ENQUEUE, headers=auth_headers(USER_A))

    # Assert — 403 naming the setting, and nothing was enqueued (gated everywhere enqueue happens).
    # (The refusal's correlation id is bound to the structlog context via bind_request_id, not the
    # error-response headers — FastAPI does not carry the injected Response headers through an
    # HTTPException, the same as the keyless 403.)
    assert response.status_code == 403
    assert "settings" in response.json()["detail"].lower()
    assert await queue.claim(worker_id="probe") is None


async def test_enqueue_stamps_the_tenants_length_and_voice(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — the caller chose a 90s lesson length and turned narration OFF.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_config = InMemoryUserConfigStore()
    await user_config.set(user_id=USER_A, key="videoLessonSeconds", value="90")
    await user_config.set(user_id=USER_A, key="videoVoice", value="false")
    async with _build_client(
        tmp_path, queue, storage, events, user_config_store=user_config
    ) as client:
        # Act
        job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]

    # Assert — the worker will plan to the tenant's length and render silent (voice-ready).
    stored = await queue.get(job_id=job_id)
    assert stored is not None
    assert stored.config["target_seconds"] == 90
    assert stored.config["voice"] is False


# ── Gap 1: re-attach to the slot's active job ─────────────────────────────────────


async def test_active_returns_the_in_flight_job_for_the_slot(
    client: httpx.AsyncClient,
) -> None:
    # Arrange — enqueue a lesson video; it is the slot's active (non-terminal) job.
    job_a = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]

    # Act — the reader (holding the source jobId) asks for the slot's current active job.
    response = await client.get(f"/api/videos/{job_a}/active", headers=auth_headers(USER_A))

    # Assert — the in-flight job is returned (here, the job itself, freshly queued).
    assert response.status_code == 200
    body = response.json()["job"]
    assert body["id"] == job_a
    assert body["status"] == "queued"


async def test_active_finds_a_regenerate_started_after_the_source_settled(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Arrange — the source job failed; a regenerate enqueued a NEW job for the same slot, whose id
    # the persisted (failed) artifact does not know.
    job_a = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    await queue.fail(job_id=job_a, error="qa failed")
    job_b = (
        await client.post(
            f"/api/videos/{job_a}/regenerate", headers=auth_headers(USER_A), json={"mode": "fresh"}
        )
    ).json()["job"]["id"]

    # Act — the reader still only knows the OLD (failed) job id.
    response = await client.get(f"/api/videos/{job_a}/active", headers=auth_headers(USER_A))

    # Assert — it re-attaches to the live (queued) regenerate, not the stale failed source.
    assert response.status_code == 200
    body = response.json()["job"]
    assert body["id"] == job_b
    assert body["status"] == "queued"


async def test_active_is_204_when_nothing_is_in_flight(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Arrange — the slot's only job settled; nothing is rendering.
    job_a = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    await queue.fail(job_id=job_a, error="x")

    # Act / Assert — no active job → 204, so the reader keeps its terminal state.
    response = await client.get(f"/api/videos/{job_a}/active", headers=auth_headers(USER_A))
    assert response.status_code == 204


async def test_active_is_404_for_another_users_source_job(
    client: httpx.AsyncClient,
) -> None:
    # Arrange — A's job; B must not probe it (existence never leaks across tenants).
    job_a = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]

    # Act / Assert
    response = await client.get(f"/api/videos/{job_a}/active", headers=auth_headers(USER_B))
    assert response.status_code == 404


async def test_active_resolves_a_course_level_video_slot(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Arrange — a course-level SUMMARY video (the Overview "what this course covers" slot) has no
    # lesson_id; the re-attach must resolve the slot on the null-lesson path too, not just lessons.
    await queue.enqueue(
        VideoJob(
            id="sum-1",
            user_id=USER_A,
            course_id="course-1",
            lesson_id=None,
            kind=VideoKind.SUMMARY,
            input_hash="h",
        )
    )

    # Act
    response = await client.get("/api/videos/sum-1/active", headers=auth_headers(USER_A))

    # Assert — the in-flight course-level job is returned (the Overview slot re-attaches).
    assert response.status_code == 200
    body = response.json()["job"]
    assert body["id"] == "sum-1"
    assert body["lessonId"] is None


# ── enqueue + status read ─────────────────────────────────────────────────────────


async def test_enqueue_creates_an_owner_stamped_queued_job(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Act
    response = await client.post(_ENQUEUE, headers=auth_headers(USER_A))

    # Assert — 202 with the queued job's wire shape; the row is owner-stamped, defaults stamped on.
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
    # Unset video config → product defaults: the per-kind lesson length, voice on.
    assert stored.config["target_seconds"] == 75
    assert stored.config["voice"] is True


# ── enqueue ownership + dedup (V4-T0, the V0-deferred safety) ──────────────────────


async def test_enqueue_for_an_unowned_course_is_not_found(client: httpx.AsyncClient) -> None:
    # Arrange / Act — USER_B is keyed + authed but does NOT own course-1 (seeded for USER_A).
    response = await client.post(_ENQUEUE, headers=auth_headers(USER_B))

    # Assert — 404 (missing or not-owned alike — existence is never leaked across tenants).
    assert response.status_code == 404


async def test_enqueue_for_a_missing_lesson_is_not_found(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Act — the course is owned, but it has no lesson "ghost".
    response = await client.post(
        "/api/courses/course-1/lessons/ghost/video", headers=auth_headers(USER_A)
    )

    # Assert — rejected before any job is created (the guard fires before spending capacity).
    assert response.status_code == 404
    assert await queue.claim(worker_id="probe") is None


async def test_enqueue_dedupes_an_in_flight_lesson_video(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Act — two Generate requests for the same lesson while the first is still queued/in-flight.
    first_response = await client.post(_ENQUEUE, headers=auth_headers(USER_A))
    second_response = await client.post(_ENQUEUE, headers=auth_headers(USER_A))

    # Assert — both accepted; the second returns the in-flight job, not a twin; one is claimable.
    assert first_response.status_code == 202
    assert second_response.status_code == 202
    first = first_response.json()["job"]["id"]
    second = second_response.json()["job"]["id"]
    assert first == second
    claimed = await queue.claim(worker_id="probe")
    assert claimed is not None and claimed.id == first
    assert await queue.claim(worker_id="probe") is None


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


async def test_a_ready_job_carries_grounding_provenance_to_the_wire(
    client: httpx.AsyncClient, worker: VideoWorker
) -> None:
    # Arrange — enqueue over HTTP, then the worker settles the job (and uploads provenance.json).
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True

    # Act
    response = await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))

    # Assert — provenance traverses pipeline → storage → API: the wire names the job it came from.
    # The stub video is framing-only, so it grounds on (and asserts) nothing: claimIds is empty.
    body = response.json()
    assert body["provenance"] is not None
    assert body["provenance"]["jobId"] == job_id
    assert body["provenance"]["courseId"] == "course-1"
    assert body["provenance"]["claimIds"] == []


async def _drive_to_ready(client: httpx.AsyncClient, queue: InMemoryVideoJobQueue) -> VideoJob:
    """Enqueue over HTTP and settle the job READY through the queue (no worker), so a test can
    stage its own artifacts in storage. Returns the settled job."""
    await client.post(_ENQUEUE, headers=auth_headers(USER_A))
    claimed = await queue.claim(worker_id="probe")
    assert claimed is not None
    await queue.complete(job_id=claimed.id)
    return claimed


async def test_a_ready_job_surfaces_non_empty_claim_ids_on_the_wire(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue, storage: InMemoryVideoStorage
) -> None:
    # Arrange — a READY job whose stored provenance grounds on two verified claims.
    job = await _drive_to_ready(client, queue)
    provenance = VideoProvenance(
        job_id=job.id,
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        model="claude-opus-4-8",
        contract_hash="h",
        input_hash="h",
        claim_ids=["c1", "c3"],
        generated_at="2026-01-01T00:00:00+00:00",
    )
    await storage.upload(
        path=VideoArtifactPaths.for_job(job).provenance,
        data=provenance.model_dump_json(by_alias=True).encode(),
        content_type="application/json",
    )

    # Act
    body = (await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))).json()

    # Assert — the grounded claim ids reach the wire unchanged (a grounded video, not framing-only).
    assert body["provenance"]["claimIds"] == ["c1", "c3"]


def _timing(*, voiced: bool) -> TimingManifest:
    clip = "S1_intro_b1.mp3" if voiced else None
    return TimingManifest(
        {
            "S1_intro": SceneTiming(
                beats=[
                    BeatTiming(id="b1", audio_s=1.0, anim_s=1.2, audio=clip, estimated=not voiced)
                ],
                total_s=1.2,
            )
        }
    )


async def test_a_narrated_ready_job_offers_a_signed_captions_url(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue, storage: InMemoryVideoStorage
) -> None:
    # Arrange — a READY job whose persisted timing manifest is VOICED, with a captions track staged.
    job = await _drive_to_ready(client, queue)
    paths = VideoArtifactPaths.for_job(job)
    await storage.upload(
        path=paths.timing,
        data=_timing(voiced=True).model_dump_json().encode(),
        content_type="application/json",
    )
    await storage.upload(
        path=paths.captions,
        data=b"WEBVTT\n\n00:00:00.000 --> 00:00:01.200\nHello.\n",
        content_type="text/vtt",
    )

    # Act
    body = (await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))).json()

    # Assert — the player gets a signed captions track under the job prefix.
    assert body["captionsUrl"] is not None
    assert f"{USER_A}/course-1/{job.id}/captions.vtt" in body["captionsUrl"]


async def test_a_silent_ready_job_offers_no_captions_url(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue, storage: InMemoryVideoStorage
) -> None:
    # Arrange — a READY job whose persisted timing manifest is the SILENT estimate (no clips).
    job = await _drive_to_ready(client, queue)
    paths = VideoArtifactPaths.for_job(job)
    await storage.upload(
        path=paths.timing,
        data=_timing(voiced=False).model_dump_json().encode(),
        content_type="application/json",
    )

    # Act
    body = (await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))).json()

    # Assert — a silent video has no audio, so no captions track is offered.
    assert body["captionsUrl"] is None


async def test_a_ready_job_without_provenance_degrades_to_null(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Arrange — a READY job with NO provenance.json in storage (a pre-V2 job, or one whose
    # provenance upload predates this surface). The status read must not 500.
    job = await _drive_to_ready(client, queue)

    # Act
    response = await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))

    # Assert — ready, playback URLs present, provenance gracefully absent.
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["status"] == "ready"
    assert body["videoUrl"] is not None
    assert body["provenance"] is None


async def test_an_in_flight_job_carries_no_provenance(client: httpx.AsyncClient) -> None:
    # Arrange — a freshly queued job: provenance only exists once the worker has produced.
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]

    # Act
    body = (await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))).json()

    # Assert
    assert body["job"]["status"] == "queued"
    assert body["provenance"] is None


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
    # This test proves the worker SPINE (claim → produce → upload → ready), so it pins the stub
    # pipeline: deterministic whether or not the render extra is installed (the real Manim
    # pipeline has its own smoke tests and would need a seeded course + toolchain here).
    monkeypatch.setattr("lunaris_api.app.get_video_pipeline", lambda settings: StubVideoPipeline())
    # Seed course-1/lesson-1 in the file store so the enqueue endpoint's ownership check passes (the
    # file store is single-user and ignores owner_id; the stub pipeline never loads the lesson).
    from lunaris_runtime.persistence import CourseStore

    seg = MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )
    CourseStore(tmp_path).save(
        Course(
            id="course-1",
            topic="t",
            modules=[Module(id="m1", title="S", lessons=[Lesson(id="lesson-1", segments=seg)])],
        )
    )
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


async def test_lifespan_does_not_drain_when_inproc_worker_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The cloud API posture (V7): video generation ON (so it still enqueues) but the in-process
    # worker OFF — the dedicated worker container renders. The lifespan must NOT start a worker, so
    # an enqueued job stays QUEUED here (no API stub worker stealing + stubbing it).
    from lunaris_api import dependencies
    from lunaris_runtime.persistence import CourseStore

    monkeypatch.setattr(dependencies, "_in_memory_video_queue", InMemoryVideoJobQueue())
    monkeypatch.setattr(dependencies, "_in_memory_video_storage", InMemoryVideoStorage())
    monkeypatch.setenv("VIDEO_GENERATION_ENABLED", "true")
    monkeypatch.setenv("LUNARIS_VIDEO_INPROC_WORKER", "false")  # the cloud API gate
    monkeypatch.setenv("LUNARIS_VIDEO_WORKER_POLL_S", "0.01")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("LUNARIS_PIPELINE", "stub")
    monkeypatch.setenv("LUNARIS_COURSE_DIR", str(tmp_path))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr("lunaris_api.app.get_video_pipeline", lambda settings: StubVideoPipeline())
    seg = MerrillSegments(
        activate=Segment(), demonstrate=Segment(), apply=Segment(), integrate=Segment()
    )
    CourseStore(tmp_path).save(
        Course(
            id="course-1",
            topic="t",
            modules=[Module(id="m1", title="S", lessons=[Lesson(id="lesson-1", segments=seg)])],
        )
    )
    get_settings.cache_clear()
    try:
        app = create_app()
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # Act — enqueue over HTTP (allowed: video generation is on).
                job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"][
                    "id"
                ]
                # Give any (wrongly-started) worker ample time to claim + settle it.
                await asyncio.sleep(0.2)
                body = (
                    await client.get(f"/api/videos/{job_id}", headers=auth_headers(USER_A))
                ).json()

        # Assert — the job is still QUEUED: this process never drained it.
        assert body["job"]["status"] == "queued"
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


# ── pipeline selection (the V1 stub → real swap) ────────────────────────────────


def test_video_pipeline_falls_back_to_stub_without_the_render_extra(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — simulate a lean image / CI where Manim is not installed.
    import importlib.util

    from lunaris_api.dependencies import get_video_pipeline

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a, **k: None if name == "manim" else real_find_spec(name, *a, **k),
    )

    # Act
    pipeline = get_video_pipeline(_settings(tmp_path, video_enabled=True))

    # Assert — the worker still has a pipeline (the job spine survives a missing toolchain).
    assert isinstance(pipeline, StubVideoPipeline)


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("manim") is None,
    reason="render extra not installed (make video-deps)",
)
def test_video_pipeline_is_the_real_pipeline_when_renderable(tmp_path: Path) -> None:
    # Arrange / Act — the render toolchain is present (local dev / the V7 worker image).
    from lunaris_api.dependencies import get_video_pipeline
    from lunaris_video import KindRoutingVideoPipeline

    pipeline = get_video_pipeline(_settings(tmp_path, video_enabled=True))

    # Assert — keyed renders run the real plan→render→QA→assemble pipeline, routed by kind so a
    # lesson / summary / overview job each reaches its configured inner pipeline (V5).
    assert isinstance(pipeline, KindRoutingVideoPipeline)


# ── the regenerate menu (V6-T2) ────────────────────────────────────────────────────


async def _seed_source(
    queue: InMemoryVideoJobQueue,
    *,
    kind: VideoKind = VideoKind.LESSON,
    failed: bool = False,
    config: dict | None = None,
) -> VideoJob:
    """Seed a source video job (id ``source-job``) owned by USER_A on course-1, settled READY unless
    ``failed``. A LESSON job is on lesson-1; a course kind carries no lesson. Returns the job a
    regenerate points at — the single settle-sequence authority for the regenerate tests."""
    job = VideoJob(
        id="source-job",
        user_id=USER_A,
        course_id="course-1",
        lesson_id="lesson-1" if kind is VideoKind.LESSON else None,
        kind=kind,
        input_hash="src-hash",
        config=config or {},
    )
    await queue.enqueue(job)
    await queue.claim(worker_id="seed")  # QUEUED → in-flight so it can settle terminal
    if failed:
        await queue.fail(job_id=job.id, error="render exploded")
    else:
        await queue.complete(job_id=job.id)
    return job


_REGEN = "/api/videos/source-job/regenerate"


async def test_regenerate_fresh_enqueues_a_new_job(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Arrange — a finished source video.
    await _seed_source(queue)

    # Act — Fresh take.
    response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "fresh"})

    # Assert — a brand-new job (distinct id) carrying the fresh regenerate descriptor + coordinates.
    assert response.status_code == 202, response.text
    new_job = response.json()["job"]
    assert new_job["id"] != "source-job"
    assert new_job["status"] == "queued"
    assert new_job["lessonId"] == "lesson-1"
    # config is a free-form dict, so its nested keys stay as written (model fields camelise, this
    # doesn't): regenerate carries the mode + the source job id.
    assert new_job["config"]["regenerate"]["mode"] == "fresh"
    assert new_job["config"]["regenerate"]["source_job_id"] == "source-job"


async def test_regenerate_simpler_works_from_a_failed_source(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # A re-plan mode regenerates even a failed video (there's nothing to reuse, so it re-plans).
    await _seed_source(queue, failed=True)

    response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "simpler"})

    assert response.status_code == 202
    assert response.json()["job"]["config"]["regenerate"]["mode"] == "simpler"


async def test_retry_requires_a_finished_source(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Retry reuses the prior contract — a FAILED source has none, so the reuse modes are refused.
    await _seed_source(queue, failed=True)

    response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "retry"})

    assert response.status_code == 409
    assert "fresh" in response.json()["detail"].lower()


async def test_reuse_modes_refuse_an_in_flight_source(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # The 409 guard is any non-READY status, not just FAILED — a still-rendering source has no
    # stored contract either, for both reuse modes.
    job = VideoJob(
        id="source-job",
        user_id=USER_A,
        course_id="course-1",
        lesson_id="lesson-1",
        kind=VideoKind.LESSON,
        input_hash="h",
    )
    await queue.enqueue(job)  # left QUEUED (never settled)

    for mode in ("retry", "add_narration"):
        response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": mode})
        assert response.status_code == 409, mode


async def test_add_narration_forces_voice_on_and_carries_the_contract_path(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Add narration reuses the finished contract and turns narration on regardless of the toggle.
    await _seed_source(queue)

    response = await client.post(
        _REGEN, headers=auth_headers(USER_A), json={"mode": "add_narration"}
    )

    assert response.status_code == 202
    config = response.json()["job"]["config"]
    assert config["voice"] is True
    assert config["regenerate"]["mode"] == "add_narration"
    # The reuse modes carry the source's contract storage path for the worker to load.
    assert (
        f"{USER_A}/course-1/source-job/scene_contracts.json"
        in config["regenerate"]["contract_path"]
    )


async def test_regenerate_unknown_job_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/videos/ghost/regenerate", headers=auth_headers(USER_A), json={"mode": "fresh"}
    )
    assert response.status_code == 404


async def test_regenerate_not_owned_is_404(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # The source is owned by USER_A; USER_B can't see it (existence is not leaked).
    await _seed_source(queue)
    response = await client.post(_REGEN, headers=auth_headers(USER_B), json={"mode": "fresh"})
    assert response.status_code == 404


async def test_regenerate_refused_when_video_disabled_in_settings(
    tmp_path: Path,
    queue: InMemoryVideoJobQueue,
    storage: InMemoryVideoStorage,
    events: InMemoryRunEventStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The per-user master toggle gates regenerate too (every enqueue point).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    user_config = InMemoryUserConfigStore()
    await user_config.set(user_id=USER_A, key="videoEnabled", value="false")
    await _seed_source(queue)
    async with _build_client(
        tmp_path, queue, storage, events, user_config_store=user_config
    ) as client:
        response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "fresh"})

    assert response.status_code == 403


async def test_regenerate_is_deduped_while_a_job_is_in_flight(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # A regenerate must not stack on a live job for the same coordinates — it returns the live one.
    await _seed_source(queue)
    first = (await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "fresh"})).json()
    # The first regenerate is now QUEUED (live) for course-1/lesson-1; a second returns it.
    second = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "simpler"})

    assert second.status_code == 202
    assert second.json()["job"]["id"] == first["job"]["id"]


async def test_regenerate_rejects_an_unknown_mode(client: httpx.AsyncClient) -> None:
    response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": "teleport"})
    assert response.status_code == 422


# ── staleness: the "outdated" badge (V6-T3) ────────────────────────────────────────


async def _seed_ready(
    queue: InMemoryVideoJobQueue,
    *,
    input_hash: str,
    kind: VideoKind = VideoKind.LESSON,
    lesson_id: str | None = "lesson-1",
    job_id: str = "ready-job",
) -> VideoJob:
    job = VideoJob(
        id=job_id,
        user_id=USER_A,
        course_id="course-1",
        lesson_id=lesson_id,
        kind=kind,
        input_hash=input_hash,
        config={"target_seconds": 75},
    )
    await queue.enqueue(job)
    await queue.claim(worker_id="seed")
    await queue.complete(job_id=job.id)
    return job


async def test_a_ready_lesson_video_is_not_stale_when_the_content_matches(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Built from the current lesson at the default length → the recomputed hash matches → not stale.
    fresh = lesson_video_input_hash("course-1", _seeded_lesson(), target_seconds=75)
    job = await _seed_ready(queue, input_hash=fresh)

    body = (await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))).json()

    assert body["job"]["status"] == "ready"
    assert body["stale"] is False


async def test_a_ready_lesson_video_is_stale_after_the_lesson_changes(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # Built under an old content/length hash → the current lesson recomputes differently → outdated.
    job = await _seed_ready(queue, input_hash="built-from-the-old-lesson")

    body = (await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))).json()

    assert body["stale"] is True


async def test_a_course_video_is_never_flagged_stale(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # A trailer/intro has no single lesson to revise — the staleness check never fires for it.
    job = await _seed_ready(
        queue, input_hash="anything", kind=VideoKind.SUMMARY, lesson_id=None, job_id="summary-job"
    )

    body = (await client.get(f"/api/videos/{job.id}", headers=auth_headers(USER_A))).json()

    assert body["stale"] is False


# ── variant coverage (V6-T4): regenerate x every kind; toggles/lengths gate end-to-end ──


def _source_config(kind: VideoKind) -> dict:
    # Course kinds carry the grounding snapshot the regenerate copies forward (AD-1).
    config: dict = {"target_seconds": 75}
    if kind is not VideoKind.LESSON:
        config["grounding"] = {"topic": "Algorithms"}
    return config


@pytest.mark.parametrize("kind", list(VideoKind))
@pytest.mark.parametrize("mode", ["retry", "simpler", "fresh", "add_narration"])
async def test_regenerate_variant_enters_the_pipeline_for_every_kind(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue, kind: VideoKind, mode: str
) -> None:
    # Every (mode x kind) from a finished source enqueues a job of the same kind, tagged with the
    # mode; course kinds carry grounding forward, reuse modes carry the contract path, and Add
    # narration forces voice on regardless of kind.
    await _seed_source(queue, kind=kind, config=_source_config(kind))

    response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": mode})

    assert response.status_code == 202, (kind, mode, response.text)
    new = response.json()["job"]
    assert new["kind"] == kind.value
    regenerate = new["config"]["regenerate"]
    assert regenerate["mode"] == mode
    if kind is not VideoKind.LESSON:
        assert new["config"]["grounding"]["topic"] == "Algorithms"
    if mode == "add_narration":
        assert new["config"]["voice"] is True
    if mode in ("retry", "add_narration"):
        assert "contract_path" in regenerate  # the reuse modes hand the worker the prior contract
    else:
        assert "contract_path" not in regenerate  # the re-plan modes don't read it


@pytest.mark.parametrize("kind", list(VideoKind))
@pytest.mark.parametrize("mode", ["retry", "add_narration"])
async def test_reuse_mode_refuses_a_failed_source_for_every_kind(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue, kind: VideoKind, mode: str
) -> None:
    # A reuse mode needs a finished contract — a FAILED source of any kind is a 409.
    await _seed_source(queue, kind=kind, failed=True, config=_source_config(kind))

    response = await client.post(_REGEN, headers=auth_headers(USER_A), json={"mode": mode})

    assert response.status_code == 409, (kind, mode)


async def test_regenerate_clears_the_outdated_badge(
    client: httpx.AsyncClient, queue: InMemoryVideoJobQueue
) -> None:
    # A lesson video built under an old hash reads outdated; a Fresh regenerate rebuilds from the
    # current lesson, so the regenerated job is no longer stale (the badge clears).
    await _seed_ready(queue, input_hash="built-from-the-old-lesson")
    before = (await client.get("/api/videos/ready-job", headers=auth_headers(USER_A))).json()
    assert before["stale"] is True

    regen = await client.post(
        "/api/videos/ready-job/regenerate", headers=auth_headers(USER_A), json={"mode": "fresh"}
    )
    new_id = regen.json()["job"]["id"]
    await queue.claim(worker_id="seed")
    await queue.complete(job_id=new_id)

    after = (await client.get(f"/api/videos/{new_id}", headers=auth_headers(USER_A))).json()
    assert after["job"]["status"] == "ready"
    assert after["stale"] is False
