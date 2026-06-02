"""Integration tests for the persisted, replayable build event log (build-timeline Phase B).

They traverse the real layers (HTTP → service → stub pipeline → IRunEventStore), with an in-memory
event store standing in for Supabase (no live DB in CI). Persisting is best-effort: a build must
succeed even when the event-log write fails, exactly like the run-history index.
"""

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.dependencies import get_course_service
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunEventStore, InMemoryRunStore
from lunaris_runtime.schema import RunEvent


def _client_for(service: CourseService) -> httpx.ASGITransport:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_course_service] = lambda: service
    return httpx.ASGITransport(app=app)


@pytest.fixture
def event_store() -> InMemoryRunEventStore:
    return InMemoryRunEventStore()


@pytest.fixture
async def http_with(
    tmp_path: Path, event_store: InMemoryRunEventStore
) -> AsyncIterator[httpx.AsyncClient]:
    service = CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        event_store=event_store,
    )
    transport = _client_for(service)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_stream_build_persists_a_replayable_event_log(
    http_with: httpx.AsyncClient, event_store: InMemoryRunEventStore
) -> None:
    # Arrange — build a course over the real SSE path. Reading .text is load-bearing: it drains the
    # streaming body so the pipeline (and its persistence) runs to completion before we replay.
    response = await http_with.get("/api/courses/stream", params={"topic": "graphs"})
    _ = response.text
    run_id = response.headers["x-run-id"]

    # Act — replay: read the persisted ordered log back over HTTP.
    log = await http_with.get(f"/api/runs/{run_id}/events")

    # Assert — the log replays the build: ordered, run_id-correlated, with the wire payloads intact.
    assert log.status_code == 200
    events = log.json()
    assert events, "expected the streamed build to leave a persisted event log"
    # Store-assigned seq is a gap-free 0..N-1 emission order (one queue, one counter).
    seqs = [e["seq"] for e in events]
    assert seqs == list(range(len(events)))
    # Every row carries the run's correlation id (provenance) and a known kind.
    assert all(e["runId"] == run_id for e in events)
    assert {e["kind"] for e in events} <= {"progress", "agent"}
    # Behavioral: a progress row's payload is the real camelCase ProgressEvent wire shape.
    progress = [e for e in events if e["kind"] == "progress"]
    assert progress, "expected at least the coarse progress stages in the log"
    assert "stage" in progress[0]["payload"] and "label" in progress[0]["payload"]
    assert progress[0]["payload"]["runId"] == run_id


async def test_deleting_a_course_purges_its_event_log(
    http_with: httpx.AsyncClient, event_store: InMemoryRunEventStore
) -> None:
    # Arrange — build a course so it has a persisted event log; find its course_id from a row.
    response = await http_with.get("/api/courses/stream", params={"topic": "graphs"})
    _ = response.text
    run_id = response.headers["x-run-id"]
    before = (await http_with.get(f"/api/runs/{run_id}/events")).json()
    assert before, "precondition: the build left an event log to purge"
    course_id = before[0]["courseId"]

    # Act — delete the course (the same door the sidebar/CLI use).
    deleted = await http_with.delete(f"/api/courses/{course_id}")

    # Assert — deletion succeeds and the run's event log is gone with the course.
    assert deleted.status_code == 204
    after = await http_with.get(f"/api/runs/{run_id}/events")
    assert after.json() == []


class _PurgeFailingEventStore(InMemoryRunEventStore):
    """Appends/reads normally but blows up on purge — proves purge is best-effort."""

    async def delete_for_course(self, *, course_id: str) -> int:
        raise RuntimeError("event log purge is down")


async def test_event_log_purge_failure_does_not_break_course_deletion(tmp_path: Path) -> None:
    # Arrange — a course built with an event store whose purge fails.
    event_store = _PurgeFailingEventStore()
    service = CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        event_store=event_store,
    )
    transport = _client_for(service)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/courses/stream", params={"topic": "graphs"})
        _ = response.text
        run_id = response.headers["x-run-id"]
        course_id = (await client.get(f"/api/runs/{run_id}/events")).json()[0]["courseId"]

        # Act — the course delete must still succeed despite the failing event-log purge.
        deleted = await client.delete(f"/api/courses/{course_id}")

    # Assert — best-effort: the user's deletion is not blocked by a purge failure.
    assert deleted.status_code == 204


async def test_unknown_run_has_no_build_record(http_with: httpx.AsyncClient) -> None:
    # Act — a run that never built (or a course built before Phase B shipped).
    log = await http_with.get("/api/runs/never-ran/events")

    # Assert — an empty log, not a 404: the UI renders a "no build record" empty state.
    assert log.status_code == 200
    assert log.json() == []


class _FailingEventStore:
    """An event store whose append blows up — proves persistence is best-effort."""

    async def append(self, *, events: Sequence[RunEvent]) -> None:
        raise RuntimeError("event log is down")

    async def list_for_run(self, *, run_id: str) -> list[RunEvent]:
        return []

    async def delete_for_course(self, *, course_id: str) -> int:
        return 0


async def test_event_log_write_failure_does_not_break_a_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange — an event store that fails on every append.
    service = CourseService(
        CourseStore(tmp_path),
        build_stub_orchestrator,
        InMemoryRunStore(),
        event_store=_FailingEventStore(),
    )
    transport = _client_for(service)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act — stream the whole build despite the failing log (.text drains it to completion).
        response = await client.get("/api/courses/stream", params={"topic": "graphs"})
        _ = response.text

    # Assert — the build still completed (a course frame closed the stream).
    assert response.status_code == 200
    assert "event: course" in response.text
    # Triangulate: the best-effort path ran and logged the failure run_id-correlated.
    run_id = response.headers["x-run-id"]
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    append_failures = [e for e in events if e.get("event") == "run_events_append_failed"]
    assert append_failures and all(e["run_id"] == run_id for e in append_failures)
