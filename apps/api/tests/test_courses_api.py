"""Integration tests for the delivery API — they traverse the real layers (HTTP → service →
orchestrator → CourseStore → back), with the deterministic stub pipeline so no key is needed."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.routers.courses import _sse_frame
from lunaris_api.run_registry import RunRegistry
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore
from lunaris_runtime.schema import ProgressEvent, ProgressStage, RunStatus


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        env_file=tmp_path / ".env",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_healthz_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_create_course_returns_camelcase_course_object(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.post("/api/courses", json={"topic": "binary search"})

    # Assert — 201 with a published course-object serialized camelCase (the web contract)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "published"
    assert body["graph"]["nodes"]  # graph built
    assert body["graph"]["topoOrder"][-1] == body["goalConcept"]  # camelCase alias present
    assert response.headers["x-run-id"]  # correlation id surfaced


async def test_create_course_carries_lesson_content(client: httpx.AsyncClient) -> None:
    # Act
    body = (await client.post("/api/courses", json={"topic": "binary search"})).json()

    # Assert — the wire contract the lesson/reader view consumes: modules carry lessons, each lesson
    # carries the four Merrill segments (camelCase), and a segment carries prose + claims + visuals.
    module = body["modules"][0]
    assert module["lessons"], "module must carry lessons for the reader to render"
    segments = module["lessons"][0]["segments"]
    assert set(segments) == {"activate", "demonstrate", "apply", "integrate"}
    activate = segments["activate"]
    assert isinstance(activate["prose"], str)
    assert isinstance(activate["claims"], list)
    assert isinstance(activate["visuals"], list)
    # Assessment items serialize camelCase alongside the lesson content.
    assert isinstance(module["assessment"]["items"], list)


async def test_stub_course_carries_a_branded_visual_spec(client: httpx.AsyncClient) -> None:
    # Arrange — no extra setup; the client runs the stub pipeline (its visual engine emits a spec).

    # Act
    body = (await client.post("/api/courses", json={"topic": "binary search"})).json()

    # Assert — a typed VisualSpec rides a demonstrate visual, serialized camelCase for the reader.
    visuals = [
        visual
        for module in body["modules"]
        for lesson in module["lessons"]
        for visual in lesson["segments"]["demonstrate"]["visuals"]
    ]
    assert visuals, "the stub pipeline should attach demonstrate visuals"
    spec = next((visual["spec"] for visual in visuals if visual.get("spec")), None)
    assert spec is not None, "a demonstrate visual should carry a branded spec"
    assert spec["type"] in {"flow", "tree", "steps", "comparison", "timeline"}
    # camelCase wire contract: no snake_case keys leak through (e.g. flow edges carry `from`).
    assert all("_" not in key for key in spec)


async def test_create_then_fetch_roundtrips_by_id(client: httpx.AsyncClient) -> None:
    # Arrange
    created = (await client.post("/api/courses", json={"topic": "binary search"})).json()

    # Act
    fetched = await client.get(f"/api/courses/{created['id']}")

    # Assert
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


async def test_unknown_course_is_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/courses/does-not-exist")

    assert response.status_code == 404


async def test_regenerate_lesson_returns_the_updated_course(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — a built course with a known lesson.
    created = (await client.post("/api/courses", json={"topic": "binary search"})).json()
    course_id = created["id"]
    lesson_id = created["modules"][0]["lessons"][0]["id"]

    # Act
    response = await client.post(f"/api/courses/{course_id}/lessons/{lesson_id}/regenerate")

    # Assert — 200 with the same course, the lesson re-authored + re-illustrated.
    assert response.status_code == 200
    run_id = response.headers["x-run-id"]
    body = response.json()
    assert body["id"] == course_id
    lesson = next(
        lesson
        for module in body["modules"]
        for lesson in module["lessons"]
        if lesson["id"] == lesson_id
    )
    assert lesson["segments"]["demonstrate"]["visuals"]

    # Assert — the same run_id threads the orchestrator's regenerate log (cross-layer correlation).
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    regenerated = [e for e in events if e.get("event") == "lesson_regenerated"]
    assert regenerated and all(e["run_id"] == run_id for e in regenerated)


async def test_regenerate_unknown_lesson_is_404(client: httpx.AsyncClient) -> None:
    # Arrange — a real course, so the course_id is valid but the lesson id is fabricated.
    created = (await client.post("/api/courses", json={"topic": "binary search"})).json()

    # Act
    response = await client.post(f"/api/courses/{created['id']}/lessons/ghost/regenerate")

    # Assert
    assert response.status_code == 404


async def test_regenerate_with_an_unsupported_pipeline_is_501(tmp_path: Path) -> None:
    # Arrange — a pipeline that builds courses but can't regenerate a single lesson (the deep-agent
    # shape). It satisfies CoursePipeline but not LessonRegenerator.
    from lunaris_api.dependencies import get_course_service
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore
    from lunaris_runtime.schema import Course, CourseStatus

    class _NoRegenPipeline:
        def __init__(self, store: "object") -> None:
            self._store = store

        async def run(
            self,
            topic,
            *,
            course_id,
            run_id,
            progress=None,
            agent=None,
            clarification=None,
            discovery_depth=None,
            official_only=None,
        ):  # type: ignore[no-untyped-def]
            return Course(id=course_id, topic=topic, status=CourseStatus.PUBLISHED)

    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _NoRegenPipeline)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        # Act
        response = await http.post("/api/courses/any/lessons/any/regenerate")

    # Assert
    assert response.status_code == 501


async def test_blank_topic_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/courses", json={"topic": ""})

    assert response.status_code == 422  # Pydantic validation at the boundary


def _parse_sse(body: str) -> list[tuple[str | None, dict]]:
    """Parse an SSE body into (event-name, json-data) frames."""
    frames: list[tuple[str | None, dict]] = []
    for block in body.strip().split("\n\n"):
        event: str | None = None
        data: str | None = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        if data is not None:
            frames.append((event, json.loads(data)))
    return frames


async def test_stream_yields_ordered_progress_then_final_course(client: httpx.AsyncClient) -> None:
    # Act — the EventSource-style endpoint (GET, query param) streams the build.
    response = await client.get("/api/courses/stream", params={"topic": "binary search"})

    # Assert — transport contract: SSE content type + correlation id (sent before the body).
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    run_id = response.headers["x-run-id"]
    # The course id is also sent up front (before the body) so a client whose stream drops can
    # re-attach to the durable build by polling this id for the finished course. It's a uuid4 hex.
    course_id = response.headers["x-course-id"]
    assert len(course_id) == 32 and course_id.isalnum()

    # Assert — frame contract: ordered progress stages, then exactly one terminal course.
    frames = _parse_sse(response.text)
    progress = [data for name, data in frames if name == "progress"]
    course_frames = [data for name, data in frames if name == "course"]

    # Ordered stage backbone, run_id-correlated.
    stages = [p["stage"] for p in progress]
    assert stages[0] == "run_started"
    assert stages[-1] == "run_completed"
    assert "graph_built" in stages and "claims_verified" in stages
    assert all(p["runId"] == run_id for p in progress)  # camelCase wire contract

    # Exactly one final course frame, carrying the published course-object.
    assert len(course_frames) == 1
    course = course_frames[0]
    assert course["status"] == "published"
    assert course["graph"]["nodes"]
    assert course["graph"]["topoOrder"][-1] == course["goalConcept"]


def test_sse_frame_encodes_a_heartbeat_as_an_ignored_comment() -> None:
    # A heartbeat is an SSE comment line (": …") — it keeps an idle connection alive through a
    # silent build stretch and is ignored by the browser's EventSource, so it reaches no handler.
    assert _sse_frame("heartbeat", None) == ": keepalive\n\n"
    # A real event still encodes as a named SSE event with camelCase JSON data (the wire contract).
    frame = _sse_frame(
        "progress", ProgressEvent(stage=ProgressStage.RUN_STARTED, label="Starting", run_id="r1")
    )
    assert frame.startswith("event: progress\ndata: {")
    assert '"runId": "r1"' in frame or '"runId":"r1"' in frame
    assert frame.endswith("\n\n")


async def test_stream_blank_topic_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/courses/stream", params={"topic": ""})

    assert response.status_code == 422  # query-param validation at the boundary


async def test_stream_continues_build_after_early_disconnect(
    tmp_path: Path,
    releasable_build: tuple[Callable[[object], object], asyncio.Event],
) -> None:
    # Arrange — a gated build so we can deterministically abandon the stream mid-flight (the way a
    # disconnecting EventSource client does) before the build finishes. The build is a durable
    # background job: a disconnect must NOT cancel it; it runs to completion and records its status.
    factory, release = releasable_build
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    service = CourseService(CourseStore(tmp_path), factory, run_store, registry)
    stream = service.stream("binary search", course_id="c-cancel", run_id="run-cancel")

    # Act — consume one progress event, capture the durable build task, then close the generator
    # early (client gone). aclose must be prompt and idempotent, and must NOT cancel the build.
    kind, _payload = await stream.__anext__()
    assert kind == "progress"
    build_task = registry.task_for("run-cancel")
    assert build_task is not None
    await stream.aclose()
    await stream.aclose()  # idempotent: a second close is a no-op

    # Assert — released, the build finishes on its own and records COMPLETED (disconnect-proof),
    # rather than being killed by the disconnect. Await the task directly (deterministic).
    release.set()
    await build_task
    runs = await run_store.list_recent()
    assert runs[0].status is RunStatus.COMPLETED
    assert runs[0].module_count > 0


async def test_stream_run_id_correlates_to_pipeline_logs(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # Act
    response = await client.get("/api/courses/stream", params={"topic": "binary search"})
    _ = response.text  # drain the stream so the pipeline runs to completion
    run_id = response.headers["x-run-id"]

    # Assert — the same run_id threads the orchestrator's structured logs.
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    completed = [e for e in events if e.get("event") == "course_run_completed"]
    assert completed and all(e["run_id"] == run_id for e in completed)


async def test_run_id_correlates_request_to_pipeline_logs(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # Act
    response = await client.post("/api/courses", json={"topic": "binary search"})
    run_id = response.headers["x-run-id"]

    # Assert — the same run_id appears in the orchestrator's structured logs
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    completed = [e for e in events if e.get("event") == "course_run_completed"]
    assert completed and all(e["run_id"] == run_id for e in completed)


class _AgentEventPipeline:
    """A minimal CoursePipeline that emits one progress stage + one agent transcript beat, then
    returns a tiny published course. Proves the SSE multiplex carries the new ``agent`` frame
    end-to-end without needing the full deep-agent harness (that path is covered separately)."""

    def __init__(self, store: "object") -> None:
        self._store = store

    async def run(  # type: ignore[no-untyped-def]
        self,
        topic,
        *,
        course_id,
        run_id,
        progress=None,
        agent=None,
        clarification=None,
        discovery_depth=None,
        official_only=None,
    ):
        from lunaris_agent.harness.agent_reporter import AgentReporter
        from lunaris_agent.harness.progress_reporter import ProgressReporter
        from lunaris_runtime.schema import (
            AgentEventKind,
            Course,
            CourseStatus,
            ProgressStage,
        )

        await ProgressReporter(run_id, progress).emit(ProgressStage.RUN_STARTED, "start")
        await AgentReporter(run_id, agent).emit(
            AgentEventKind.TOOL_CALL, tool="extract_concepts", tool_args={"topic": topic}
        )
        await ProgressReporter(run_id, progress).emit(
            ProgressStage.RUN_COMPLETED, "done", status=CourseStatus.PUBLISHED
        )
        return Course(id=course_id, topic=topic, status=CourseStatus.PUBLISHED)


class _ClarificationSpyPipeline:
    """Records the clarification the service forwarded, proving the API parses the opt-in confirm
    answers (P7.5) off the build request and threads them into ``pipeline.run`` (where the agent
    pipeline folds them onto the inferred brief). Captures into a shared dict keyed by run_id."""

    captured: ClassVar[dict[str, object]] = {}

    def __init__(self, store: "object") -> None:
        self._store = store

    async def run(  # type: ignore[no-untyped-def]
        self,
        topic,
        *,
        course_id,
        run_id,
        progress=None,
        agent=None,
        clarification=None,
        discovery_depth=None,
        official_only=None,
    ):
        from lunaris_agent.harness.progress_reporter import ProgressReporter
        from lunaris_runtime.schema import Course, CourseStatus, ProgressStage

        _ClarificationSpyPipeline.captured["clarification"] = clarification
        _ClarificationSpyPipeline.captured["discovery_depth"] = discovery_depth
        _ClarificationSpyPipeline.captured["official_only"] = official_only
        await ProgressReporter(run_id, progress).emit(ProgressStage.RUN_STARTED, "start")
        await ProgressReporter(run_id, progress).emit(
            ProgressStage.RUN_COMPLETED, "done", status=CourseStatus.PUBLISHED
        )
        return Course(id=course_id, topic=topic, status=CourseStatus.PUBLISHED)


async def _send_stream_request(tmp_path: Path, params: dict) -> httpx.Response:
    """Drive the stream endpoint against the clarification spy and return the raw response.

    Resets the spy's shared capture first, so every test that touches it is independent of order.
    """
    from lunaris_api.dependencies import get_course_service
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore

    _ClarificationSpyPipeline.captured = {}
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _ClarificationSpyPipeline)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get("/api/courses/stream", params=params)


async def _stream_with_clarification(tmp_path: Path, params: dict) -> "object":
    """Drive the stream endpoint and return the clarification the spy pipeline was handed."""
    response = await _send_stream_request(tmp_path, params)
    assert response.status_code == 200
    return _ClarificationSpyPipeline.captured["clarification"]


async def test_stream_forwards_the_clarification_to_the_pipeline(tmp_path: Path) -> None:
    # Arrange — a camelCase clarification on the build request (the web's wire shape).
    from lunaris_runtime.schema import Clarification, Level

    clarification = json.dumps({"targetLevel": "advanced", "assumedKnown": "the beginner ladder"})

    # Act
    forwarded = await _stream_with_clarification(
        tmp_path, {"topic": "binary search", "clarification": clarification}
    )

    # Assert — parsed into the typed Clarification and threaded to the pipeline unchanged.
    assert forwarded == Clarification(
        target_level=Level.ADVANCED, assumed_known="the beginner ladder"
    )


async def test_stream_without_a_clarification_forwards_none(tmp_path: Path) -> None:
    # Act — the default one-click path: no clarification query param.
    forwarded = await _stream_with_clarification(tmp_path, {"topic": "binary search"})

    # Assert — the pipeline is driven with no clarification (today's inferred-only build).
    assert forwarded is None


async def test_stream_forwards_the_chosen_discovery_depth(tmp_path: Path) -> None:
    from lunaris_runtime.schema import DiscoveryDepth

    # Act — the learner pre-authorized a deeper search (P6.3).
    response = await _send_stream_request(
        tmp_path, {"topic": "binary search", "discovery_depth": "thorough"}
    )

    # Assert — the depth is parsed into the typed enum and threaded to the pipeline.
    assert response.status_code == 200
    assert _ClarificationSpyPipeline.captured["discovery_depth"] is DiscoveryDepth.THOROUGH


async def test_stream_defaults_discovery_depth_to_standard(tmp_path: Path) -> None:
    # Act — no discovery_depth query param (the one-click default).
    from lunaris_runtime.schema import DiscoveryDepth

    response = await _send_stream_request(tmp_path, {"topic": "binary search"})

    # Assert — the pipeline runs at the moderate STANDARD depth.
    assert response.status_code == 200
    assert _ClarificationSpyPipeline.captured["discovery_depth"] is DiscoveryDepth.STANDARD


async def test_stream_forwards_official_only_to_the_pipeline(tmp_path: Path) -> None:
    # Act — the composer's "Official sources only" switch (P5) is on for this build.
    response = await _send_stream_request(
        tmp_path, {"topic": "binary search", "official_only": "true"}
    )

    # Assert — the flag is parsed to a bool and threaded to the pipeline (→ Draft → verifier floor).
    assert response.status_code == 200
    assert _ClarificationSpyPipeline.captured["official_only"] is True


async def test_stream_defaults_official_only_to_false(tmp_path: Path) -> None:
    # Act — no official_only query param (today's build, unchanged trust floor).
    response = await _send_stream_request(tmp_path, {"topic": "binary search"})

    # Assert — the pipeline runs with the switch off.
    assert response.status_code == 200
    assert _ClarificationSpyPipeline.captured["official_only"] is False


async def test_stream_rejects_an_invalid_discovery_depth(tmp_path: Path) -> None:
    # Act — an out-of-vocabulary depth.
    response = await _send_stream_request(
        tmp_path, {"topic": "binary search", "discovery_depth": "exhaustive"}
    )

    # Assert — rejected at the boundary by the enum-typed query param.
    assert response.status_code == 422


async def test_stream_rejects_a_malformed_clarification(tmp_path: Path) -> None:
    # Act — not valid JSON for a Clarification.
    response = await _send_stream_request(tmp_path, {"topic": "x", "clarification": "not-json"})

    # Assert — rejected at the boundary, not silently ignored.
    assert response.status_code == 422


async def test_stream_rejects_a_clarification_with_an_invalid_enum(tmp_path: Path) -> None:
    # Act — valid JSON, but "superexpert" is not a Level.
    response = await _send_stream_request(
        tmp_path, {"topic": "x", "clarification": json.dumps({"targetLevel": "superexpert"})}
    )

    # Assert — schema validation at the boundary, not a 500 downstream.
    assert response.status_code == 422


async def test_stream_rejects_an_overlong_free_text_field(tmp_path: Path) -> None:
    # Act — assumedKnown exceeds the schema's 1000-char cap (a prompt-bloat guard).
    overlong = json.dumps({"assumedKnown": "x" * 1001})
    response = await _send_stream_request(tmp_path, {"topic": "x", "clarification": overlong})

    # Assert
    assert response.status_code == 422


async def test_stream_forwards_an_empty_clarification_object_as_defaults(tmp_path: Path) -> None:
    # Arrange — an empty {} is a valid all-default Clarification (the identity), distinct from None.
    from lunaris_runtime.schema import Clarification

    # Act
    forwarded = await _stream_with_clarification(tmp_path, {"topic": "x", "clarification": "{}"})

    # Assert — parsed to a default Clarification (which apply_clarification treats as the identity).
    assert forwarded == Clarification()


async def test_create_forwards_the_clarification_from_the_post_body(tmp_path: Path) -> None:
    # Arrange — the await-full POST path carries the clarification in the JSON body.
    from lunaris_api.dependencies import get_course_service
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore
    from lunaris_runtime.schema import Clarification, Level

    _ClarificationSpyPipeline.captured = {}
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _ClarificationSpyPipeline)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        # Act
        response = await http.post(
            "/api/courses",
            json={
                "topic": "binary search",
                "clarification": {"targetLevel": "expert", "background": "a working engineer"},
            },
        )

    # Assert — parsed off the body and threaded to the pipeline as the typed model.
    assert response.status_code == 201
    assert _ClarificationSpyPipeline.captured["clarification"] == Clarification(
        target_level=Level.EXPERT, background="a working engineer"
    )


async def test_create_forwards_the_discovery_depth_from_the_post_body(tmp_path: Path) -> None:
    # Arrange — the await-full POST path carries the chosen discovery depth (P6.3).
    from lunaris_api.dependencies import get_course_service
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore
    from lunaris_runtime.schema import DiscoveryDepth

    _ClarificationSpyPipeline.captured = {}
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _ClarificationSpyPipeline)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        # Act
        response = await http.post(
            "/api/courses", json={"topic": "binary search", "discovery_depth": "thorough"}
        )

    # Assert — parsed off the body and threaded to the pipeline as the typed enum.
    assert response.status_code == 201
    assert _ClarificationSpyPipeline.captured["discovery_depth"] is DiscoveryDepth.THOROUGH


async def test_create_forwards_official_only_from_the_post_body(tmp_path: Path) -> None:
    # Arrange — the await-full POST path carries the "Official sources only" switch (P5), matching
    # the GET /stream coverage so both build entry points are proven, not just one.
    from lunaris_api.dependencies import get_course_service
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore

    _ClarificationSpyPipeline.captured = {}
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _ClarificationSpyPipeline)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        # Act
        response = await http.post(
            "/api/courses", json={"topic": "binary search", "official_only": True}
        )

    # Assert — parsed off the body and threaded to the pipeline (→ Draft → verifier floor).
    assert response.status_code == 201
    assert _ClarificationSpyPipeline.captured["official_only"] is True


async def test_stream_carries_agent_transcript_frames(tmp_path: Path) -> None:
    # Arrange — the API wired to a pipeline that emits a progress stage AND an agent beat.
    from lunaris_api.dependencies import get_course_service
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore

    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _AgentEventPipeline)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        # Act
        response = await http.get("/api/courses/stream", params={"topic": "binary search"})

    # Assert — a new `agent` frame rides the same stream as progress + the terminal course.
    assert response.status_code == 200
    run_id = response.headers["x-run-id"]
    frames = _parse_sse(response.text)
    names = [name for name, _ in frames]
    assert "progress" in names and "agent" in names and names[-1] == "course"

    agent_frames = [data for name, data in frames if name == "agent"]
    assert len(agent_frames) == 1
    beat = agent_frames[0]
    assert beat["kind"] == "tool_call"
    assert beat["tool"] == "extract_concepts"
    assert beat["toolArgs"] == {"topic": "binary search"}  # camelCase wire contract
    assert beat["runId"] == run_id  # cross-layer correlation


async def test_rebuild_reuses_the_course_id(client: httpx.AsyncClient) -> None:
    # Arrange — build a course (stub pipeline).
    created = await client.post("/api/courses", json={"topic": "binary search"})
    course_id = created.json()["id"]
    original_run_id = created.headers["X-Run-Id"]

    # Act — re-ground it (re-run the pipeline reusing the same id).
    rebuilt = await client.post(f"/api/courses/{course_id}/rebuild")

    # Assert — 200, the SAME course id, and a FRESH run id (a distinct, traceable re-ground run).
    assert rebuilt.status_code == 200
    assert rebuilt.json()["id"] == course_id
    assert rebuilt.headers.get("X-Run-Id")
    assert rebuilt.headers["X-Run-Id"] != original_run_id


async def test_rebuild_unknown_course_is_404(client: httpx.AsyncClient) -> None:
    # Act / Assert — a well-formed but never-assigned course id (ids are uuid4().hex) → 404.
    response = await client.post(f"/api/courses/{'0' * 32}/rebuild")
    assert response.status_code == 404
