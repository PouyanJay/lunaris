"""Integration tests for the delivery API — they traverse the real layers (HTTP → service →
orchestrator → CourseStore → back), with the deterministic stub pipeline so no key is needed."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_runtime.logging import clear_correlation


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(),
        secrets_path=tmp_path / "secrets.json",
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


async def test_stream_blank_topic_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/courses/stream", params={"topic": ""})

    assert response.status_code == 422  # query-param validation at the boundary


async def test_stream_cancels_pipeline_on_early_disconnect(tmp_path: Path) -> None:
    # Arrange — drive the service's stream directly so we can abandon it mid-flight,
    # the way a disconnecting EventSource client does.
    from lunaris_agent import build_stub_orchestrator
    from lunaris_api.service import CourseService
    from lunaris_runtime.persistence import CourseStore

    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator)
    stream = service.stream("binary search", course_id="c-cancel", run_id="run-cancel")

    # Act — consume one progress event, then close the generator early (client gone).
    kind, _payload = await stream.__anext__()
    assert kind == "progress"
    await stream.aclose()  # runs the finally → cancels the background run task

    # Assert — aclose returns promptly without hanging or raising; a second close is a no-op.
    await stream.aclose()


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

    async def run(self, topic, *, course_id, run_id, progress=None, agent=None):  # type: ignore[no-untyped-def]
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
