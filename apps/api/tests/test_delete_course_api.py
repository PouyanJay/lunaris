"""Integration tests for DELETE /api/courses/{id} — purging a course and its per-course assets.
They traverse the real HTTP → service → CourseStore + RunStore path with the deterministic stub
pipeline (no key) and a fresh in-memory run store so both deletions are observable."""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.dependencies import get_course_service
from lunaris_api.service import CourseService, InvalidCourseIdError
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore


@pytest.fixture
def run_store() -> InMemoryRunStore:
    return InMemoryRunStore()


@pytest.fixture
async def client(tmp_path: Path, run_store: InMemoryRunStore) -> AsyncIterator[httpx.AsyncClient]:
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def test_delete_removes_the_course_file_and_run_row(
    client: httpx.AsyncClient, tmp_path: Path
) -> None:
    # Arrange — build a course (writes <id>.json AND records a run row).
    created = (await client.post("/api/courses", json={"topic": "binary search"})).json()
    course_id = created["id"]
    assert (tmp_path / f"{course_id}.json").exists()

    # Act
    response = await client.delete(f"/api/courses/{course_id}")

    # Assert — 204, and BOTH assets are actually gone (verify real state, not just the status code).
    assert response.status_code == 204
    assert not (tmp_path / f"{course_id}.json").exists(), "the course file must be deleted"
    assert (await client.get(f"/api/courses/{course_id}")).status_code == 404
    runs = (await client.get("/api/runs")).json()
    assert all(run["id"] != course_id for run in runs), "the run-history row must be deleted"


# Routable-over-HTTP unsafe ids (single path segment, no `/`), each a distinct rejected char class:
# a dot, a doubled dot, and an (encoded) space — all outside the [A-Za-z0-9_-] allowlist → 400.
@pytest.mark.parametrize("bad_id", ["with.dot", "a..b", "has space"])
async def test_delete_rejects_unsafe_course_ids_with_400(
    client: httpx.AsyncClient, bad_id: str
) -> None:
    response = await client.delete(f"/api/courses/{bad_id}")

    assert response.status_code == 400


# Ids that can't reach the handler as a single URL path segment (slashes, empty) — proven at the
# service door, where the guard fires BEFORE any unlink, not at the URL router that normalizes them.
@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "a/b/c", ""])
async def test_delete_rejects_unsafe_ids_at_the_service(tmp_path: Path, bad_id: str) -> None:
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, InMemoryRunStore())

    with pytest.raises(InvalidCourseIdError):
        await service.delete_course(bad_id)


async def test_delete_blocks_a_running_run_with_409(
    client: httpx.AsyncClient, run_store: InMemoryRunStore
) -> None:
    # Arrange — a run mid-build (RUNNING, no persisted course yet).
    await run_store.start(run_id="r-1", course_id="c-running", topic="graphs")

    # Act
    response = await client.delete("/api/courses/c-running")

    # Assert — blocked with 409, and the row is NOT removed (deletion didn't happen).
    assert response.status_code == 409
    assert await run_store.get(course_id="c-running") is not None


async def test_delete_unknown_course_is_404(client: httpx.AsyncClient) -> None:
    # Neither a file nor a run row exists → nothing to delete.
    response = await client.delete("/api/courses/doesnotexist")

    assert response.status_code == 404


async def test_delete_emits_a_structured_log_for_the_course(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange
    created = (await client.post("/api/courses", json={"topic": "binary search"})).json()
    course_id = created["id"]
    capsys.readouterr()  # drop the build's logs so we assert only on the delete

    # Act
    response = await client.delete(f"/api/courses/{course_id}")
    request_id = response.headers["x-request-id"]

    # Assert — a course_deleted log names the course and carries the request_id from the response
    # header, so a deletion is traceable across layers by a single correlation id.
    events = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    deleted = [e for e in events if e.get("event") == "course_deleted"]
    assert deleted and deleted[0]["course_id"] == course_id
    assert deleted[0]["file_deleted"] is True and deleted[0]["row_deleted"] is True
    assert deleted[0]["request_id"] == request_id
