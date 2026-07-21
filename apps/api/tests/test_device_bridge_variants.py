"""Device-bridge variant coverage (device-build-bridge T5) — the journey's final parametrized
pass over the bridge's boundaries:

- ownership: another user's bridge reads as 404 (never an existence leak);
- input bounds: oversized result text / request id, an out-of-range long-poll wait, and an
  unknown compute value are rejected at the boundary;
- the keyed invariant: a keyed build ignores ``compute=device`` entirely (no bridge exists);
- isolation: two concurrent device builds each get THEIR tab's answers, never each other's.

Hermetic (HS256 tokens, in-memory stores, probe pipelines) — no live services.
"""

import asyncio
import time
from pathlib import Path

import httpx
import pytest
from _auth import JWT_SECRET, USER_A, USER_B, auth_headers
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_device_bridge_registry
from lunaris_api.device_bridge_registry import DeviceBridgeRegistry
from lunaris_api.schemas import ComputeChoice
from lunaris_api.service import CourseService
from lunaris_runtime.device_bridge import DeviceBridge
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore
from test_device_bridge_api import BridgeProbePipeline, _build_bridge_client

# --- ownership: a foreign bridge is indistinguishable from a missing one -------------------------


@pytest.fixture
async def owned_bridge_client(tmp_path: Path):
    """An auth-ON app whose registry already holds USER_A's bridge for run ``run-a``."""
    clear_correlation()
    app = create_app()
    registry = DeviceBridgeRegistry()
    registry.register("run-a", DeviceBridge(run_id="run-a"), USER_A)
    app.dependency_overrides[get_device_bridge_registry] = lambda: registry
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
        supabase_jwt_secret=JWT_SECRET,  # auth ON
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_another_users_bridge_reads_as_not_found(owned_bridge_client) -> None:
    # Act — USER_B probes USER_A's run id on both bridge surfaces.
    poll = await owned_bridge_client.get(
        "/api/runs/run-a/bridge/requests", params={"wait": 0}, headers=auth_headers(USER_B)
    )
    post = await owned_bridge_client.post(
        "/api/runs/run-a/bridge/results",
        json={"requestId": "r1", "text": "hijack"},
        headers=auth_headers(USER_B),
    )

    # Assert — both read as "no such bridge", indistinguishable from an unknown run.
    assert poll.status_code == 404
    assert post.status_code == 404


async def test_the_owner_can_poll_their_own_bridge(owned_bridge_client) -> None:
    # Act / Assert — the same probe by the owner is a normal (empty) work feed, proving the
    # 404 above was ownership, not absence.
    poll = await owned_bridge_client.get(
        "/api/runs/run-a/bridge/requests", params={"wait": 0}, headers=auth_headers(USER_A)
    )
    assert poll.status_code == 200
    assert poll.json() == []


# --- input bounds at the HTTP boundary ------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "described_as"),
    [
        ({"requestId": "r1", "text": "x" * 200_001}, "oversized result text"),
        ({"requestId": "r" * 65, "text": "fine"}, "oversized request id"),
    ],
)
async def test_an_out_of_bounds_result_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict, described_as: str
) -> None:
    # Arrange — a real device build with a live bridge, so the 422 is the bound, not a 404.
    client, _, registry = _build_bridge_client(tmp_path, monkeypatch)
    async with client:
        stream_task = asyncio.create_task(
            client.get("/api/courses/stream", params={"topic": "x", "compute": "device"})
        )
        run_ids = await _await_bridges(registry, 1, stream_task)
        assert run_ids, "the device build never registered a bridge"
        run_id = run_ids[0]

        # Act
        response = await client.post(f"/api/runs/{run_id}/bridge/results", json=payload)

        # Assert — rejected at the boundary; the build is then released so the test ends clean
        # (the cleanup legs are asserted too, so a masked secondary failure can't hide here).
        assert response.status_code == 422, described_as
        poll = await client.get(f"/api/runs/{run_id}/bridge/requests", params={"wait": 4.0})
        assert poll.status_code == 200, poll.text
        for request in poll.json():
            answered = await client.post(
                f"/api/runs/{run_id}/bridge/results",
                json={"requestId": request["requestId"], "text": "ok"},
            )
            assert answered.status_code == 204, answered.text
        await stream_task


async def _await_bridges(
    registry: DeviceBridgeRegistry, count: int, *builds: asyncio.Task
) -> list[str]:
    """Wait for ``count`` builds to register their bridges, bounded by wall-clock, not by a fixed
    number of loop yields — on a loaded runner a build needs more turns than any spin budget
    guesses, which is exactly how this read went flaky in CI. A build that dies first re-raises
    here rather than surfacing as a bare "no bridge" a step later."""
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        run_ids = _registry_run_ids(registry)
        if len(run_ids) >= count:
            return run_ids
        for build in builds:
            if build.done():
                build.result()  # a crashed build: re-raise its error instead of timing out on it
        if builds and all(build.done() for build in builds):
            break  # every build finished without a bridge — waiting longer can't change that
        await asyncio.sleep(0.01)
    return _registry_run_ids(registry)


def _registry_run_ids(registry: DeviceBridgeRegistry) -> list[str]:
    """The registry's in-flight run ids — a test-only peek (the registry deliberately exposes no
    enumeration; httpx's ASGITransport buffers whole responses, so X-Run-Id can't be read live).
    Ids only: ownership is NOT visible here — assert it through the HTTP surface."""
    return list(registry._bridges)


async def test_an_overlong_poll_wait_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — wait is capped so a client can't park requests for minutes.
    client, _, _ = _build_bridge_client(tmp_path, monkeypatch)

    # Act / Assert
    async with client:
        response = await client.get("/api/runs/any/bridge/requests", params={"wait": 31})
    assert response.status_code == 422


async def test_an_unknown_compute_value_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    client, _, _ = _build_bridge_client(tmp_path, monkeypatch)

    # Act / Assert — the enum boundary, not a silent server-compute fallback.
    async with client:
        response = await client.get(
            "/api/courses/stream", params={"topic": "x", "compute": "mainframe"}
        )
    assert response.status_code == 422


# --- the keyed invariant --------------------------------------------------------------------------


async def test_a_keyed_build_ignores_the_device_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — an Anthropic key is present: the build is hosted, whatever the dropdown says.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    registry = DeviceBridgeRegistry()
    service = CourseService(
        CourseStore(tmp_path),
        lambda store: BridgeProbePipeline(store),
        InMemoryRunStore(),
        bridge_registry=registry,
    )

    # Act
    admission = await service.admit_build(None, compute=ComputeChoice.DEVICE, run_id="run-keyed")

    # Assert — no bridge was admitted or registered; the run is a normal hosted build.
    assert admission.device_bridge is None
    assert registry.lookup("run-keyed") is None


# --- isolation: two concurrent device builds, two tabs, no cross-wiring ---------------------------


async def test_concurrent_device_builds_each_get_their_own_tabs_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — one app, two device builds racing; each "tab" answers with its own run's text.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    clear_correlation()
    app = create_app()
    registry = DeviceBridgeRegistry()
    pipelines: list[BridgeProbePipeline] = []

    def factory(store):
        pipeline = BridgeProbePipeline(store)
        pipelines.append(pipeline)
        return pipeline

    service = CourseService(
        CourseStore(tmp_path), factory, InMemoryRunStore(), bridge_registry=registry
    )
    from lunaris_api.dependencies import get_course_service

    app.dependency_overrides[get_course_service] = lambda: service
    app.dependency_overrides[get_device_bridge_registry] = lambda: registry
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)

    async def serve_run(client: httpx.AsyncClient, run_id: str) -> None:
        poll = await client.get(f"/api/runs/{run_id}/bridge/requests", params={"wait": 4.0})
        for request in poll.json():
            await client.post(
                f"/api/runs/{run_id}/bridge/results",
                json={"requestId": request["requestId"], "text": f"answer-for-{run_id}"},
            )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act — start both builds, learn both run ids from the registry, serve each bridge.
        first = asyncio.create_task(
            client.get("/api/courses/stream", params={"topic": "alpha", "compute": "device"})
        )
        second = asyncio.create_task(
            client.get("/api/courses/stream", params={"topic": "beta", "compute": "device"})
        )
        run_ids = await _await_bridges(registry, 2, first, second)
        assert len(run_ids) == 2, "both device builds should have live bridges"
        await asyncio.gather(*(serve_run(client, run_id) for run_id in run_ids))
        await asyncio.gather(first, second)

    # Assert — each pipeline saw exactly its own bridge's answer (run-scoped contextvars: no
    # cross-wiring even with both builds in flight on one event loop).
    replies = sorted(p.last_reply for p in pipelines)
    assert replies == sorted(f"answer-for-{run_id}" for run_id in run_ids)
