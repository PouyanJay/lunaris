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
from _doubles import CannotResizeCoverStorage
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.cover_display_transform import COVER_DISPLAY_TRANSFORM
from lunaris_api.dependencies import (
    get_course_store,
    get_cover_job_queue,
    get_cover_storage,
)
from lunaris_covers import CoverWorker, StubCoverPipeline
from lunaris_covers.models.rendered_cover import RenderedCover
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import (
    CoverArtifactPaths,
    InMemoryCoverJobQueue,
    InMemoryCoverStorage,
)
from lunaris_runtime.schema import Course, CoverJobStatus, CoverLightMode


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
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")  # the caller is keyed (env path, no vault)
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
    assert prov["source"] == "stub"
    assert prov["model"] == "stub"
    assert prov["stylePreset"] == "general"

    # Assert (behaviour, not surface) — the image landed in storage as real PNG bytes, and the
    # cover was folded onto the course payload as course material.
    paths = CoverArtifactPaths.for_coordinates(USER_A, "course-1", job_id)
    assert storage.read(paths.image)[:8] == b"\x89PNG\r\n\x1a\n"
    course = course_store.load("course-1", owner_id=USER_A)
    assert course.cover is not None
    assert course.cover.status == CoverJobStatus.READY
    assert course.cover.job_id == job_id


# ── dual-theme: the READY view carries a light URL only when a light variant exists ──


class _DualThemePipeline:
    """A pipeline double that produced BOTH a dark and a light image (a dual-theme cover)."""

    async def produce(self, job, *, on_stage) -> RenderedCover:  # type: ignore[no-untyped-def]
        base = await StubCoverPipeline().produce(job, on_stage=on_stage)
        return RenderedCover(
            image=base.image,
            image_light=base.image + b"L",
            provenance=base.provenance.model_copy(
                update={"has_light_variant": True, "light_mode": CoverLightMode.RETHEME}
            ),
        )


async def test_ready_view_carries_a_light_url_for_a_dual_theme_cover(
    client: httpx.AsyncClient,
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
) -> None:
    # A worker whose pipeline produced both variants → the READY view exposes both signed URLs, so
    # the web can show the dark image in light theme and the light image in dark theme.
    worker = CoverWorker(
        queue=queue,
        pipeline=_DualThemePipeline(),
        storage=storage,
        course_store=course_store,  # type: ignore[arg-type]
        worker_id="dual-worker-test",
    )
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True

    body = (await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))).json()
    assert body["job"]["status"] == CoverJobStatus.READY.value
    assert body["imageUrl"]  # the dark cover
    assert body["imageUrlLight"]  # the light twin
    assert body["imageUrl"] != body["imageUrlLight"]  # two distinct objects
    # The light object really landed in storage under the light path.
    paths = CoverArtifactPaths.for_coordinates(USER_A, "course-1", job_id)
    assert storage.read(paths.image_light) == storage.read(paths.image) + b"L"


# ── display derivatives: the card/Overview surfaces get a resized thumb, the lightbox the master ──


async def test_ready_view_carries_a_resized_thumb_alongside_the_master(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    # A cover master is 2048x1152; a card frame is ~260px wide. Shipping the master to the card and
    # letting the browser shrink it is what makes a card cover look soft, so the view carries a
    # SEPARATE storage-resized derivative for the display surfaces. The master URL stays untouched —
    # the full-size lightbox must not be silently served a downscale.
    job_id = await _enqueue_ready(client, worker)

    body = (await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))).json()

    assert body["imageUrl"]
    assert body["thumbUrl"]
    assert body["thumbUrl"] != body["imageUrl"]  # a distinct mint, not the master with params
    assert f"width={COVER_DISPLAY_TRANSFORM.width}" in body["thumbUrl"]
    assert "width=" not in body["imageUrl"]  # the master is served whole


async def test_display_derivative_is_sharp_at_every_surface_and_dpr() -> None:
    # The derivative must out-resolve the largest frame that shows it at the highest DPR we support,
    # or we would have swapped a browser downscale for a browser UPSCALE — visibly worse. The widest
    # frame is the ~420px card track (grid: minmax(260px, 1fr)); 3x is the top device-pixel ratio.
    widest_frame_css_px = 420
    assert COVER_DISPLAY_TRANSFORM.width >= widest_frame_css_px * 3
    # And it keeps the cover's native 16:9, so the server-side crop is a no-op on a correct render.
    assert COVER_DISPLAY_TRANSFORM.width / COVER_DISPLAY_TRANSFORM.height == 16 / 9


async def test_ready_view_carries_a_light_thumb_only_for_a_dual_theme_cover(
    client: httpx.AsyncClient,
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
) -> None:
    # The thumb dimension is orthogonal to the light/dark one: a dual-theme cover gets a derivative
    # for BOTH variants, so the dark-theme app shows a sharp LIGHT card, not a downscaled one.
    worker = CoverWorker(
        queue=queue,
        pipeline=_DualThemePipeline(),
        storage=storage,
        course_store=course_store,  # type: ignore[arg-type]
        worker_id="dual-thumb-worker-test",
    )
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True

    body = (await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))).json()

    assert f"width={COVER_DISPLAY_TRANSFORM.width}" in body["thumbUrlLight"]  # really resized
    assert body["thumbUrlLight"] != body["imageUrlLight"]  # the light master is still whole
    assert body["thumbUrlLight"] != body["thumbUrl"]  # and it is the LIGHT object's derivative


async def test_ready_view_omits_the_light_thumb_for_a_dark_only_cover(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    # No light object exists, so no light derivative may be minted — a signed URL for a missing
    # object would render as a broken image rather than falling back to the dark cover.
    job_id = await _enqueue_ready(client, worker)
    body = (await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))).json()
    assert body["thumbUrlLight"] is None


async def test_ready_view_still_serves_the_master_when_the_thumb_cannot_be_minted(
    tmp_path: Path,
    queue: InMemoryCoverJobQueue,
    course_store: _FakeCourseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The derivative is an OPTIMIZATION, not the cover. A backend that cannot resize must not take
    # the whole view down with it: the master and provenance resolved fine beside it, and the reader
    # falls back to the master — so the cover renders softer, never missing (and never a 500).
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    storage = CannotResizeCoverStorage()
    worker = CoverWorker(
        queue=queue,
        pipeline=StubCoverPipeline(),
        storage=storage,
        course_store=course_store,  # type: ignore[arg-type]
        worker_id="no-resize-worker-test",
    )
    async with _build_client(tmp_path, queue, storage, course_store) as client:
        job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
        assert await worker.run_once() is True

        response = await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))

        assert response.status_code == 200  # NOT a 500
        body = response.json()
        assert body["imageUrl"]  # the cover still renders, at the master
        assert body["thumbUrl"] is None  # the derivative simply isn't offered
        assert body["provenance"] is not None  # and provenance survived alongside it


async def test_ready_view_omits_the_light_url_for_a_dark_only_cover(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    # The stub pipeline produces a dark-only cover (no light variant) → no light URL is minted, so
    # the reader shows the dark image in both themes (like a pre-dual-theme cover).
    job_id = await _enqueue_ready(client, worker)
    body = (await client.get(f"/api/covers/{job_id}", headers=auth_headers(USER_A))).json()
    assert body["imageUrl"]
    assert body["imageUrlLight"] is None


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
    # Correlation survives the failure path: the id rides on the HTTPException, not the discarded
    # request-scoped Response (the reader/log can still triangulate a 404).
    assert resp.headers.get("X-Request-Id")


async def test_status_404_still_carries_the_request_id(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/covers/does-not-exist", headers=auth_headers(USER_A))
    assert resp.status_code == 404
    assert resp.headers.get("X-Request-Id")


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


# ── the OpenAI-key tier gate (T3): keyless enqueue is refused, so the reader shows Typographic ──


async def test_keyless_caller_cannot_enqueue(
    tmp_path: Path,
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — authed + owns the course, but NO OpenAI key (env path, no vault).
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    async with _build_client(tmp_path, queue, storage, course_store) as keyless:
        # Act / Assert — 403 (a keyed-tier feature), so the web falls back to the Typographic cover.
        resp = await keyless.post(_ENQUEUE, headers=auth_headers(USER_A))
        assert resp.status_code == 403


# ── T7: active (re-attach) / regenerate / cancel ────────────────────────────────────


async def _enqueue_ready(client: httpx.AsyncClient, worker: CoverWorker) -> str:
    """Enqueue a cover for course-1 and drain it to READY; return its job id."""
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    assert await worker.run_once() is True
    return job_id


async def test_active_returns_the_in_flight_job(client: httpx.AsyncClient) -> None:
    # A cover is enqueued but not yet drained — /active re-attaches the reader to the live job.
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    resp = await client.get(f"/api/covers/{job_id}/active", headers=auth_headers(USER_A))
    assert resp.status_code == 200
    assert resp.json()["job"]["id"] == job_id
    assert resp.headers.get("X-Request-Id")


async def test_active_returns_a_settled_regenerate_newer_than_the_source(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    # The reader holds the FIRST cover's id; a regenerate settles under a NEW id. /active surfaces
    # the newer READY cover (with signed URL + provenance) so a completed regenerate persists.
    source_id = await _enqueue_ready(client, worker)
    regen = await client.post(f"/api/covers/{source_id}/regenerate", headers=auth_headers(USER_A))
    new_id = regen.json()["job"]["id"]
    assert await worker.run_once() is True  # drain the regenerate to READY

    resp = await client.get(f"/api/covers/{source_id}/active", headers=auth_headers(USER_A))
    assert resp.status_code == 200
    body = resp.json()
    assert body["job"]["id"] == new_id
    assert body["imageUrl"]  # a READY active job carries the signed URL + provenance
    assert body["provenance"] is not None


async def test_active_204_when_nothing_newer_than_the_source(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    source_id = await _enqueue_ready(client, worker)
    resp = await client.get(f"/api/covers/{source_id}/active", headers=auth_headers(USER_A))
    assert resp.status_code == 204
    assert resp.headers.get("X-Request-Id")


async def test_active_is_owner_scoped_404(client: httpx.AsyncClient, worker: CoverWorker) -> None:
    source_id = await _enqueue_ready(client, worker)
    resp = await client.get(f"/api/covers/{source_id}/active", headers=auth_headers(USER_B))
    assert resp.status_code == 404
    assert resp.headers.get("X-Request-Id")


async def test_regenerate_enqueues_a_fresh_job(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    source_id = await _enqueue_ready(client, worker)
    resp = await client.post(f"/api/covers/{source_id}/regenerate", headers=auth_headers(USER_A))
    assert resp.status_code == 202
    assert resp.headers.get("X-Request-Id")
    new_id = resp.json()["job"]["id"]
    assert new_id != source_id
    assert resp.json()["job"]["status"] == CoverJobStatus.QUEUED.value


async def test_regenerate_dedups_an_in_flight_job(client: httpx.AsyncClient) -> None:
    # A regenerate while one is already generating returns the in-flight job, never a second.
    source_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    resp = await client.post(f"/api/covers/{source_id}/regenerate", headers=auth_headers(USER_A))
    assert resp.status_code == 202
    assert resp.json()["job"]["id"] == source_id


async def test_regenerate_is_keyless_gated_403(
    tmp_path: Path,
    queue: InMemoryCoverJobQueue,
    storage: InMemoryCoverStorage,
    course_store: _FakeCourseStore,
    worker: CoverWorker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    async with _build_client(tmp_path, queue, storage, course_store) as keyed:
        source_id = await _enqueue_ready(keyed, worker)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    async with _build_client(tmp_path, queue, storage, course_store) as keyless:
        resp = await keyless.post(
            f"/api/covers/{source_id}/regenerate", headers=auth_headers(USER_A)
        )
        assert resp.status_code == 403


async def test_regenerate_unknown_job_404(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/covers/nope/regenerate", headers=auth_headers(USER_A))
    assert resp.status_code == 404
    assert resp.headers.get("X-Request-Id")


async def test_cancel_stops_a_queued_job(client: httpx.AsyncClient) -> None:
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    resp = await client.post(f"/api/covers/{job_id}/cancel", headers=auth_headers(USER_A))
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == CoverJobStatus.CANCELLED.value
    assert resp.headers.get("X-Request-Id")


async def test_cancel_is_owner_scoped_404(client: httpx.AsyncClient) -> None:
    job_id = (await client.post(_ENQUEUE, headers=auth_headers(USER_A))).json()["job"]["id"]
    resp = await client.post(f"/api/covers/{job_id}/cancel", headers=auth_headers(USER_B))
    assert resp.status_code == 404
    assert resp.headers.get("X-Request-Id")


async def test_cancel_is_idempotent_on_a_terminal_job(
    client: httpx.AsyncClient, worker: CoverWorker
) -> None:
    # Cancelling an already-READY cover is a no-op that returns its current (terminal) state.
    job_id = await _enqueue_ready(client, worker)
    resp = await client.post(f"/api/covers/{job_id}/cancel", headers=auth_headers(USER_A))
    assert resp.status_code == 200
    assert resp.json()["job"]["status"] == CoverJobStatus.READY.value
