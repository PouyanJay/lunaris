"""Integration tests for run-history recording — they traverse the real layers (HTTP → service →
stub pipeline → RunStore), with an in-memory RunStore standing in for Supabase (no live DB in CI).

Recording is best-effort: a build must succeed even when the history write fails."""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.dependencies import get_course_service
from lunaris_api.run_registry import RunRegistry
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore, PersistenceError
from lunaris_runtime.schema import CourseRun, RunStatus


def _client_for(service: CourseService) -> httpx.ASGITransport:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_course_service] = lambda: service
    return httpx.ASGITransport(app=app)


@pytest.fixture
def run_store() -> InMemoryRunStore:
    return InMemoryRunStore()


@pytest.fixture
async def http_with(
    tmp_path: Path, run_store: InMemoryRunStore
) -> AsyncIterator[httpx.AsyncClient]:
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store)
    transport = _client_for(service)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_post_course_records_a_completed_run(
    http_with: httpx.AsyncClient, run_store: InMemoryRunStore
) -> None:
    # Act — build a course over the real HTTP → service → pipeline path.
    response = await http_with.post("/api/courses", json={"topic": "binary search"})

    # Assert — the build succeeded and left exactly one COMPLETED run in the history.
    assert response.status_code == 201
    course = response.json()
    runs = await run_store.list_recent()
    assert len(runs) == 1
    run = runs[0]
    assert run.topic == "binary search"
    assert run.status == RunStatus.COMPLETED
    # Behavioral: the recorded counts match the artifact actually produced (not a surface check).
    assert run.kc_count == len(course["graph"]["nodes"])
    assert run.module_count == len(course["modules"])
    # Correlation: the run is keyed by course_id and carries the request's run_id.
    assert run.id == course["id"]
    assert run.run_id == response.headers["x-run-id"]


async def test_stream_build_records_a_completed_run(
    http_with: httpx.AsyncClient, run_store: InMemoryRunStore
) -> None:
    # Act — the SSE build path must record history too, not only the POST path.
    response = await http_with.get("/api/courses/stream", params={"topic": "graphs"})
    _ = response.text  # drain the stream so the pipeline runs to completion

    # Assert
    assert response.status_code == 200
    runs = await run_store.list_recent()
    assert len(runs) == 1
    assert runs[0].status == RunStatus.COMPLETED
    assert runs[0].topic == "graphs"
    assert runs[0].kc_count > 0
    assert runs[0].module_count > 0
    assert runs[0].run_id == response.headers["x-run-id"]


class _FailingRunStore:
    """A RunStore whose every write blows up with the backend-failure contract error
    (``PersistenceError`` — what the Supabase stores raise) — proves recording is best-effort."""

    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None:
        raise PersistenceError("history index is down")

    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None:
        raise PersistenceError("history index is down")

    async def list_recent(self, *, limit: int = 50, owner_id: str | None = None) -> list[CourseRun]:
        return []


class _BuggyRunStore:
    """A RunStore with a programming error (not a backend failure) — must NOT be hidden."""

    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None:
        raise TypeError("start() got an unexpected keyword argument")

    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None:
        return None

    async def list_recent(self, *, limit: int = 50, owner_id: str | None = None) -> list[CourseRun]:
        return []


async def test_a_programming_error_in_the_run_store_is_not_swallowed(tmp_path: Path) -> None:
    # Arrange — a store whose failure is a bug in our code, not an unavailable backend. The
    # best-effort guards catch only PersistenceError; anything else must surface loudly.
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, _BuggyRunStore())
    transport = _client_for(service)

    # Act / Assert — the bug propagates instead of degrading to "history quietly skipped".
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(TypeError):
            await client.post("/api/courses", json={"topic": "graphs"})


class _FinishFailingRunStore:
    """Start succeeds, finish blows up — exercises the _record_finish best-effort guard, which the
    start-failure case can't reach (it never gets to finish)."""

    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None:
        return None

    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None:
        raise PersistenceError("history index is down")

    async def list_recent(self, *, limit: int = 50, owner_id: str | None = None) -> list[CourseRun]:
        return []


async def test_history_write_failure_does_not_break_a_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — wire a RunStore that fails on every call.
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, _FailingRunStore())
    transport = _client_for(service)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        response = await client.post("/api/courses", json={"topic": "binary search"})

    # Assert — the build still succeeds despite the history write failing.
    assert response.status_code == 201
    assert response.json()["status"] == "published"

    # Triangulate: the best-effort path actually ran (not silently skipped) and the failure is
    # logged run_id-correlated, so a missing history row is diagnosable from the logs.
    run_id = response.headers["x-run-id"]
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    start_failures = [e for e in events if e.get("event") == "run_history_start_failed"]
    assert start_failures and all(e["run_id"] == run_id for e in start_failures)


async def test_history_finish_failure_does_not_break_a_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — start succeeds so the run reaches the finish write, which then fails.
    service = CourseService(
        CourseStore(tmp_path), build_stub_orchestrator, _FinishFailingRunStore()
    )
    transport = _client_for(service)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        response = await client.post("/api/courses", json={"topic": "binary search"})

    # Assert — the build still succeeds, and the finish-write failure is logged (not muted).
    assert response.status_code == 201
    assert response.json()["status"] == "published"
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    assert any(e.get("event") == "run_history_finish_failed" for e in events)


async def test_stream_records_completed_run_when_build_finishes_after_disconnect(
    tmp_path: Path,
    releasable_build: tuple[Callable[[object], object], asyncio.Event],
) -> None:
    """Regression: a build that finishes *after* the SSE consumer abandons the stream must be
    recorded COMPLETED — not left stuck RUNNING. The build is a durable background task that records
    its own terminal status; a disconnect no longer cancels it."""
    # Arrange — a build parked mid-flight (recorded RUNNING) until we release it.
    clear_correlation()
    factory, release = releasable_build
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    service = CourseService(CourseStore(tmp_path), factory, run_store, registry)

    # Act — consume the first beat (build is mid-flight, RUNNING), capture the durable build task,
    # then close the stream the way a disconnecting client does, BEFORE the course frame.
    stream = service.stream("graphs", course_id="c1", run_id="r1")
    kind, _payload = await stream.__anext__()
    assert kind == "progress"
    assert (await run_store.list_recent())[0].status is RunStatus.RUNNING  # precondition
    build_task = registry.task_for("r1")
    assert build_task is not None
    await stream.aclose()

    # Release the parked build and await it directly (deterministic — no polling): with no consumer
    # attached it must still run to completion and record its OWN terminal status.
    release.set()
    await build_task

    # Assert — recorded COMPLETED (the build really finished), not stuck RUNNING and not FAILED.
    runs = await run_store.list_recent()
    assert runs[0].status is RunStatus.COMPLETED
    assert runs[0].module_count > 0


class _FailingPipeline:
    """A pipeline whose run blows up — drives the failed-build lifecycle."""

    def __init__(self, store: object) -> None:
        self._store = store

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
    ) -> object:
        raise RuntimeError("pipeline boom")


async def test_failed_build_is_recorded_as_a_failed_run(tmp_path: Path) -> None:
    # Arrange — a real RunStore behind a pipeline that fails mid-build. raise_app_exceptions=False
    # so the transport returns the 500 Starlette produces in production instead of re-raising.
    clear_correlation()
    run_store = InMemoryRunStore()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), _FailingPipeline, run_store)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        response = await client.post("/api/courses", json={"topic": "binary search"})

    # Assert — the request errors, and the run started RUNNING then flipped to FAILED in history.
    assert response.status_code >= 500
    runs = await run_store.list_recent()
    assert len(runs) == 1
    assert runs[0].status == RunStatus.FAILED
