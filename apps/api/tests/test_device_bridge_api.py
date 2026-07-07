"""Walking skeleton for the device build bridge (device-build-bridge T0).

A keyless build started with ``compute=device`` serves its LLM completions from the learner's
browser: the run's chat model parks each completion on a per-run bridge, the tab polls it over
HTTP, and the text the tab posts back becomes the model's reply inside the pipeline. The test
traverses the real layers — HTTP stream -> service (bridge run-scope) -> ``build_chat_model``
(runtime) -> bridge router <- a fake tab — with the trivial behavior of one echoed completion.
"""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_course_service, get_device_bridge_registry
from lunaris_api.device_bridge_registry import DeviceBridgeRegistry
from lunaris_api.service import CourseService
from lunaris_runtime.device_bridge import BridgeLimits
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, ICourseStore, InMemoryRunStore
from lunaris_runtime.resilience import build_chat_model
from lunaris_runtime.schema import Course

_TAB_REPLY = "pong from the tab"


class BridgeProbePipeline:
    """A stub-course pipeline whose single LLM call routes through ``build_chat_model``.

    The skeleton's trivial behavior: the reply text (served by the fake tab) is captured on
    ``last_reply`` so the test can assert the completion really crossed the bridge, then the
    deterministic stub orchestrator assembles a real course.
    """

    def __init__(self, store: ICourseStore) -> None:
        self._inner = build_stub_orchestrator(store)
        self.last_reply: str | None = None

    async def run(
        self,
        topic: str,
        *,
        course_id: str,
        run_id: str,
        progress: object | None = None,
        agent: object | None = None,
        clarification: object | None = None,
        discovery_depth: object | None = None,
        official_only: object | None = None,
    ) -> Course:
        model = build_chat_model("claude-irrelevant")  # keyless + bridge scope → the device bridge
        reply = await model.ainvoke("ping")
        self.last_reply = reply.content if isinstance(reply.content, str) else None
        return await self._inner.run(
            topic,
            course_id=course_id,
            run_id=run_id,
            progress=progress,
            agent=agent,
            clarification=clarification,
            discovery_depth=discovery_depth,
        )


def _build_bridge_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    bridge_limits: BridgeLimits | None = None,
    raise_app_exceptions: bool = True,
) -> tuple[httpx.AsyncClient, BridgeProbePipeline, DeviceBridgeRegistry]:
    """A keyless app whose course pipeline makes one bridged LLM call — the shared Arrange."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # keyless → the Draft/bridge path
    clear_correlation()
    app = create_app()
    registry = DeviceBridgeRegistry()
    pipeline = BridgeProbePipeline(CourseStore(tmp_path))
    service = CourseService(
        CourseStore(tmp_path),
        lambda store: pipeline,
        InMemoryRunStore(),
        bridge_registry=registry,
        bridge_limits=bridge_limits,
    )
    app.dependency_overrides[get_course_service] = lambda: service
    app.dependency_overrides[get_device_bridge_registry] = lambda: registry
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return client, pipeline, registry


@pytest.fixture
async def bridge_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, BridgeProbePipeline, DeviceBridgeRegistry]]:
    """An app whose course pipeline makes one bridged LLM call, in a keyless environment."""
    client, pipeline, registry = _build_bridge_client(tmp_path, monkeypatch)
    async with client:
        yield client, pipeline, registry


async def _poll_and_answer_one_completion(client: httpx.AsyncClient, run_id: str) -> list[dict]:
    """The fake tab: one long-poll (the claim parks until the pipeline enqueues — same event
    loop, so no retry spin is needed), then answer the claimed request."""
    poll = await client.get(f"/api/runs/{run_id}/bridge/requests", params={"wait": 4.0})
    assert poll.status_code == 200, poll.text
    requests = poll.json()
    assert requests, "the bridge never offered the pipeline's completion request"
    posted = await client.post(
        f"/api/runs/{run_id}/bridge/results",
        json={"requestId": requests[0]["requestId"], "text": _TAB_REPLY},
    )
    assert posted.status_code == 204, posted.text
    return requests


async def test_device_build_serves_its_completion_from_the_tab(
    bridge_app: tuple[httpx.AsyncClient, BridgeProbePipeline, DeviceBridgeRegistry],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange — observe bridge registration to learn the run_id. The real tab reads it from the
    # X-Run-Id header before the body streams; httpx's ASGITransport buffers the whole body, so
    # the test discovers it here instead — the claim/result roundtrip below is still real HTTP.
    client, pipeline, registry = bridge_app
    registered: list[str] = []
    bridge_registered = asyncio.Event()
    original_register = registry.register
    monkeypatch.setattr(
        registry,
        "register",
        lambda run_id, bridge, owner_id=None: (
            registered.append(run_id),
            bridge_registered.set(),
            original_register(run_id, bridge, owner_id),
        ),
    )

    # Act — start a device-compute build and, like the real tab, serve its completion while
    # the build is running.
    stream_task = asyncio.create_task(
        client.get("/api/courses/stream", params={"topic": "hello", "compute": "device"})
    )
    await asyncio.wait_for(bridge_registered.wait(), timeout=5.0)
    run_id = registered[0]
    served = await _poll_and_answer_one_completion(client, run_id)
    response = await stream_task

    # Assert — the tab's text became the model's reply inside the pipeline (the full roundtrip),
    # the tab saw the pipeline's prompt, and the build still finished with a course frame whose
    # X-Run-Id matches the bridge the tab polled.
    assert response.status_code == 200, response.text
    assert response.headers["x-run-id"] == run_id
    assert pipeline.last_reply == _TAB_REPLY
    assert served[0]["messages"] == [{"role": "user", "content": "ping"}]
    assert "event: course" in response.text

    # The run_id threads through the layers' structured logs (cross-layer triangulation).
    logged = [line for line in capsys.readouterr().out.splitlines() if run_id in line]
    assert logged, "expected structured log lines carrying the run_id"


async def test_server_compute_build_registers_no_bridge(
    bridge_app: tuple[httpx.AsyncClient, BridgeProbePipeline, DeviceBridgeRegistry],
) -> None:
    client, _, _ = bridge_app

    # Act — ask about a bridge for a run that was never started as a device build.
    response = await client.get("/api/runs/no-such-run/bridge/requests", params={"wait": 0})

    # Assert — there is no bridge to poll: the tab gets a 404, not an empty offer.
    assert response.status_code == 404


async def test_device_build_fails_when_the_tab_never_polls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The explicit contract: a device build whose tab goes silent DIES — promptly, recorded
    FAILED, never a hung run. (The web makes this visible: "keep this tab open".)"""
    # Arrange — a device-compute app with a tight liveness window and NO tab.
    # raise_app_exceptions=False: a real client experiences the disconnect as the SSE stream
    # ending early, not as the server-side exception ASGITransport would otherwise re-raise.
    client, pipeline, _ = _build_bridge_client(
        tmp_path,
        monkeypatch,
        bridge_limits=BridgeLimits(liveness_s=0.05, completion_timeout_s=1.0),
        raise_app_exceptions=False,
    )
    async with client:
        # Act — start the build; nobody ever polls the bridge.
        response = await client.get(
            "/api/courses/stream", params={"topic": "hello", "compute": "device"}
        )
        runs = (await client.get("/api/runs")).json()

    # Assert — the stream ended without a course frame, the run is recorded FAILED, and the
    # pipeline never received a reply.
    assert response.status_code == 200
    assert "event: course" not in response.text
    assert [run["status"] for run in runs] == ["failed"]
    assert pipeline.last_reply is None
