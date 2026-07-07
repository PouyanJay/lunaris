"""Integration tests for the course-library list (``GET /api/courses``) — the My-courses screen's
data source. They traverse the real layers (HTTP → service → run index + course store → summary
views) with the deterministic stub pipeline, so a summary reflects a course that was actually
built and persisted, not a fixture row.

Hermetic: per-test in-memory run store (the process-wide singleton would leak rows across tests)
and a tmp-dir course store.
"""

import re
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.dependencies import get_run_store
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import InMemoryRunStore, IRunStore, PersistenceError
from lunaris_runtime.schema import CourseRun, RunStatus

_REQUEST_ID = re.compile(r"[0-9a-f]{32}")
_DEV_ORIGIN = "http://localhost:5173"  # the Vite dev server, in the CORS allowlist


def _build_client(tmp_path: Path, run_store: IRunStore) -> httpx.AsyncClient:
    clear_correlation()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub",
        course_dir=tmp_path,
        cors_origins=(_DEV_ORIGIN,),
        env_file=tmp_path / ".env",
    )
    app.dependency_overrides[get_run_store] = lambda: run_store
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def run_store() -> InMemoryRunStore:
    return InMemoryRunStore()


@pytest.fixture
async def client(tmp_path: Path, run_store: InMemoryRunStore) -> AsyncIterator[httpx.AsyncClient]:
    async with _build_client(tmp_path, run_store) as http_client:
        yield http_client


async def test_library_is_empty_before_any_build(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.get("/api/courses")

    # Assert — a fresh account has an empty library, not an error.
    assert response.status_code == 200
    assert response.json() == []


async def test_library_lists_a_built_course(client: httpx.AsyncClient) -> None:
    # Arrange — build one course through the real stub pipeline (persists course + run row).
    created = await client.post("/api/courses", json={"topic": "binary search"})
    assert created.status_code == 201
    course_id = created.json()["id"]

    # Act
    response = await client.get("/api/courses")

    # Assert — one summary on the camelCase wire, carrying the end-to-end facts the library
    # cards render, and a request id for cross-layer log triangulation.
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    summary = body[0]
    assert summary["id"] == course_id
    assert summary["topic"] == "binary search"
    assert summary["lessonTotal"] >= 1
    assert _REQUEST_ID.fullmatch(response.headers["X-Request-Id"])


async def test_run_without_a_persisted_course_is_omitted(
    client: httpx.AsyncClient, run_store: InMemoryRunStore
) -> None:
    # Arrange — one real build, plus a run row whose course never persisted (a build still
    # running, or one that died before finalize — the AD1 skip case).
    await client.post("/api/courses", json={"topic": "binary search"})
    await run_store.start(run_id="run-ghost", course_id="ghost", topic="phantom build")

    # Act
    response = await client.get("/api/courses")

    # Assert — the courseless run is skipped, not raised; the real course still lists.
    assert response.status_code == 200
    assert [summary["topic"] for summary in response.json()] == ["binary search"]


class _UnavailableRunStore:
    """A run store whose reads fail — models the history backend being unavailable. Writes are
    no-ops because recording is best-effort; only ``list_recent`` raises, which is what the
    library's read must survive."""

    async def start(
        self, *, run_id: str, course_id: str, topic: str, owner_id: str | None = None
    ) -> None: ...

    async def finish(
        self,
        *,
        course_id: str,
        status: RunStatus,
        kc_count: int,
        module_count: int,
        owner_id: str | None = None,
    ) -> None: ...

    async def list_recent(self, *, limit: int = 50, owner_id: str | None = None) -> list[CourseRun]:
        raise PersistenceError("history backend unavailable")


async def test_unavailable_backend_returns_503_with_cors_headers(tmp_path: Path) -> None:
    # Arrange — a service whose run store fails on read (missing table / outage).

    # Act — the browser sends an Origin; the library must get a recoverable answer back.
    async with _build_client(tmp_path, _UnavailableRunStore()) as http_client:
        response = await http_client.get("/api/courses", headers={"Origin": _DEV_ORIGIN})

    # Assert — a backend outage is a recoverable 503, NOT a 500: a 500 escapes the CORS
    # middleware, loses its Access-Control-Allow-Origin header, and reads as a network failure
    # instead of the library's designed Retry state.
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == _DEV_ORIGIN
