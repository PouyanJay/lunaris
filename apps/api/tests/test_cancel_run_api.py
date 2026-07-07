"""Integration tests for run cancellation — POST /api/runs/{run_id}/cancel and the service path.
A run is cancelled by signalling its in-flight task through the registry; the run's own teardown
records CANCELLED (distinct from FAILED). A controllable blocking pipeline makes the mid-build
cancellation deterministic (the stub pipeline finishes too fast to interrupt)."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.dependencies import get_course_service
from lunaris_api.run_registry import RunRegistry
from lunaris_api.service import (
    CourseBuildCancelledError,
    CourseService,
    RunNotCancellableError,
)
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore
from lunaris_runtime.schema import Course, RunStatus


class _BlockingPipeline:
    """A pipeline whose run() blocks until cancelled — so a build can be caught mid-flight."""

    def __init__(self) -> None:
        self.started = asyncio.Event()

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
        self.started.set()
        await asyncio.Event().wait()  # blocks forever; cancellation raises CancelledError here
        return Course(id=course_id, topic=topic)  # pragma: no cover - never reached


@pytest.fixture
def run_store() -> InMemoryRunStore:
    return InMemoryRunStore()


@pytest.fixture
def registry() -> RunRegistry:
    return RunRegistry()


@pytest.fixture
async def client(
    tmp_path: Path, run_store: InMemoryRunStore, registry: RunRegistry
) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store, registry)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _drain(stream: AsyncIterator[object]) -> list[object]:
    return [item async for item in stream]


async def test_cancelling_an_in_flight_build_records_cancelled(tmp_path: Path) -> None:
    # Arrange — a build blocked mid-run, registered for cancellation.
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    pipeline = _BlockingPipeline()
    service = CourseService(CourseStore(tmp_path), lambda _store: pipeline, run_store, registry)

    build = asyncio.create_task(service.create("graphs", course_id="c-1", run_id="r-1"))
    await asyncio.wait_for(pipeline.started.wait(), timeout=5)  # in-flight + registered + RUNNING

    # Act — cancel it. create() converts the asyncio CancelledError into a domain error (so it can't
    # escape the request layer as a connection drop).
    await service.cancel_run("r-1")
    with pytest.raises(CourseBuildCancelledError):
        await build

    # Assert — the run is recorded CANCELLED (not FAILED, not stuck RUNNING).
    run = await run_store.get(course_id="c-1")
    assert run is not None and run.status == RunStatus.CANCELLED


async def test_post_create_cancelled_midflight_returns_409(tmp_path: Path) -> None:
    # A cancelled await-full POST must return a clean 409 — not a dropped connection (which a raw
    # CancelledError escaping Starlette would cause).
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    pipeline = _BlockingPipeline()
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), lambda _store: pipeline, run_store, registry)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        build = asyncio.create_task(http.post("/api/courses", json={"topic": "graphs"}))
        await asyncio.wait_for(pipeline.started.wait(), timeout=5)
        run_id = (await run_store.list_recent())[0].run_id

        cancel = await http.post(f"/api/runs/{run_id}/cancel")
        assert cancel.status_code == 202

        response = await asyncio.wait_for(build, timeout=5)
        assert response.status_code == 409

    assert (await run_store.list_recent())[0].status == RunStatus.CANCELLED


async def test_cancelling_a_streaming_build_records_cancelled_and_ends_cleanly(
    tmp_path: Path,
) -> None:
    # Arrange — a streaming build blocked awaiting its first event, being consumed.
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    pipeline = _BlockingPipeline()
    service = CourseService(CourseStore(tmp_path), lambda _store: pipeline, run_store, registry)
    consume = asyncio.create_task(_drain(service.stream("graphs", course_id="c-2", run_id="r-2")))
    await asyncio.wait_for(pipeline.started.wait(), timeout=5)

    # Act — cancel it; the SSE generator should end cleanly (no error frame, no exception), distinct
    # from the disconnect→FAILED path.
    await service.cancel_run("r-2")
    await asyncio.wait_for(consume, timeout=5)

    # Assert — recorded CANCELLED, not FAILED.
    run = await run_store.get(course_id="c-2")
    assert run is not None and run.status == RunStatus.CANCELLED


async def test_cancel_run_records_cancelled_itself(tmp_path: Path) -> None:
    # The Terminate control cancels server-side, then drops the SSE immediately — so the stream
    # coroutine's teardown can be cut off mid-write by the disconnect. The cancel handler must
    # therefore record CANCELLED ITSELF (it's a stable request that isn't torn down), or the run is
    # left stuck RUNNING. Here there is NO stream consumer at all: only cancel_run can record it.
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store, registry)
    await run_store.start(run_id="r-1", course_id="c-1", topic="t")  # a RUNNING row
    task: asyncio.Task[bool] = asyncio.create_task(asyncio.Event().wait())
    registry.register("r-1", task, course_id="c-1")  # in-flight, with its course

    await service.cancel_run("r-1")

    run = await run_store.get(course_id="c-1")
    assert run is not None and run.status == RunStatus.CANCELLED
    await asyncio.gather(task, return_exceptions=True)


async def test_cancel_is_owner_scoped(tmp_path: Path) -> None:
    # Per-user isolation (Phase 2): a user must not be able to terminate another user's build by
    # guessing its run_id. A non-owner cancel is indistinguishable from "nothing in-flight" (404)
    # and must leave the task running; the owner can still cancel it.
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store, registry)
    await run_store.start(run_id="r-1", course_id="c-1", topic="t", owner_id="user-a")
    task: asyncio.Task[bool] = asyncio.create_task(asyncio.Event().wait())
    registry.register("r-1", task, course_id="c-1", owner_id="user-a")

    # A non-owner is refused and the build keeps running.
    with pytest.raises(RunNotCancellableError):
        await service.cancel_run("r-1", owner_id="user-b")
    assert not task.cancelled()

    # The owner cancels successfully.
    await service.cancel_run("r-1", owner_id="user-a")
    run = await run_store.get(course_id="c-1", owner_id="user-a")
    assert run is not None and run.status == RunStatus.CANCELLED
    await asyncio.gather(task, return_exceptions=True)


async def test_cancel_does_not_overwrite_an_already_finished_run(tmp_path: Path) -> None:
    # The benign race: the pipeline completes the same turn the cancel arrives. The registry's
    # done-task guard returns nothing in-flight (404), so cancel must NOT stamp CANCELLED over a
    # run that already landed COMPLETED.
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store, registry)
    await run_store.start(run_id="r-1", course_id="c-1", topic="t")
    await run_store.finish(course_id="c-1", status=RunStatus.COMPLETED, kc_count=1, module_count=1)
    done: asyncio.Task[bool] = asyncio.create_task(asyncio.sleep(0, result=True))
    await done  # the task is finished before the cancel arrives
    registry.register("r-1", done, course_id="c-1")

    with pytest.raises(RunNotCancellableError):
        await service.cancel_run("r-1")

    run = await run_store.get(course_id="c-1")
    assert run is not None and run.status == RunStatus.COMPLETED


async def test_cancel_unknown_run_is_404(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/runs/not-in-flight/cancel")

    assert response.status_code == 404
    assert "in-flight" in response.json()["detail"]


async def test_double_cancel_is_not_cancellable_after_the_run_ends(tmp_path: Path) -> None:
    # Once a run has ended (here: by the first cancel), it's discarded from the registry — a second
    # cancel finds nothing in-flight.
    run_store = InMemoryRunStore()
    registry = RunRegistry()
    pipeline = _BlockingPipeline()
    service = CourseService(CourseStore(tmp_path), lambda _store: pipeline, run_store, registry)
    build = asyncio.create_task(service.create("graphs", course_id="c-1", run_id="r-1"))
    await asyncio.wait_for(pipeline.started.wait(), timeout=5)

    await service.cancel_run("r-1")
    with pytest.raises(CourseBuildCancelledError):
        await build

    with pytest.raises(RunNotCancellableError):
        await service.cancel_run("r-1")


async def test_a_cancelled_run_can_then_be_deleted(
    client: httpx.AsyncClient, run_store: InMemoryRunStore, tmp_path: Path
) -> None:
    # The two journeys compose: a CANCELLED run is terminal (not RUNNING), so the delete RUNNING→409
    # guard lets it through — cancel-then-delete works.
    await run_store.start(run_id="r", course_id="c-done", topic="t")
    await run_store.finish(
        course_id="c-done", status=RunStatus.CANCELLED, kc_count=0, module_count=0
    )
    (tmp_path / "c-done.json").write_text("{}")

    response = await client.delete("/api/courses/c-done")

    assert response.status_code == 204
    assert await run_store.get(course_id="c-done") is None


async def test_cancel_endpoint_signals_an_in_flight_task_and_returns_202(
    client: httpx.AsyncClient, registry: RunRegistry
) -> None:
    # Arrange — a task registered as in-flight under a run_id (stands in for a live build).
    task: asyncio.Task[bool] = asyncio.create_task(asyncio.Event().wait())
    registry.register("r-1", task, course_id="c-1")

    # Act
    response = await client.post("/api/runs/r-1/cancel")

    # Assert — 202, a correlation id is returned, and the task was actually cancelled.
    assert response.status_code == 202
    assert response.headers["x-request-id"]
    await asyncio.gather(task, return_exceptions=True)
    assert task.cancelled()
