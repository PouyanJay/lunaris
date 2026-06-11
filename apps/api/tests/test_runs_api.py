"""Integration tests for GET /api/runs — the sidebar's run-history list. They traverse the real
HTTP → service → RunStore path with an in-memory store (no live Supabase in CI)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_agent import build_stub_orchestrator
from lunaris_api.app import create_app
from lunaris_api.dependencies import get_course_service
from lunaris_api.service import CourseService
from lunaris_runtime.logging import clear_correlation
from lunaris_runtime.persistence import CourseStore, InMemoryRunStore, IRunStore, PersistenceError
from lunaris_runtime.schema import CourseRun, RunStatus


class _UnavailableRunStore:
    """A run store whose reads fail — models the history backend being unavailable (the
    ``course_runs`` table missing, Supabase unreachable). Writes are no-ops because recording is
    best-effort; only ``list_recent`` raises, which is what the sidebar's read must survive."""

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


def _client_for(tmp_path: Path, run_store: IRunStore) -> httpx.AsyncClient:
    """Wire the app over a given run store and return a client for the real HTTP → service → store
    path. Shared by the default fixture and the outage test so the setup lives in one place."""
    clear_correlation()
    app = create_app()
    service = CourseService(CourseStore(tmp_path), build_stub_orchestrator, run_store)
    app.dependency_overrides[get_course_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def run_store() -> InMemoryRunStore:
    return InMemoryRunStore()


@pytest.fixture
async def client(tmp_path: Path, run_store: InMemoryRunStore) -> AsyncIterator[httpx.AsyncClient]:
    async with _client_for(tmp_path, run_store) as http_client:
        yield http_client


async def test_runs_list_is_empty_before_any_build(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs")

    assert response.status_code == 200
    assert response.json() == []


async def test_unavailable_history_backend_returns_503_with_cors_headers(tmp_path: Path) -> None:
    # Arrange — a service whose run store fails on read (the missing-table / outage case).
    dev_origin = "http://localhost:5173"  # the Vite dev server, in the CORS allowlist

    # Act — the browser sends an Origin; the sidebar must get a recoverable answer back.
    async with _client_for(tmp_path, _UnavailableRunStore()) as http_client:
        response = await http_client.get("/api/runs", headers={"Origin": dev_origin})

    # Assert — a backend outage is a recoverable 503, NOT a 500. A 500 is raised outside the CORS
    # middleware, so its response carries no Access-Control-Allow-Origin header and the browser
    # surfaces it as a network error ("Could not reach the run history") instead of the sidebar's
    # Retry state. The 503 must keep its CORS header so the error reaches the client honestly.
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == dev_origin


async def test_run_appears_in_the_list_after_a_build(client: httpx.AsyncClient) -> None:
    # Arrange — build a course (records a run).
    create_response = await client.post("/api/courses", json={"topic": "binary search"})
    created = create_response.json()
    run_id = create_response.headers["x-run-id"]
    assert run_id  # guard: an empty header would make the correlation assertion below vacuous

    # Act
    response = await client.get("/api/runs")

    # Assert — 200 with the run, in the camelCase shape the sidebar's useRuns() consumes.
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    run = runs[0]
    assert run["id"] == created["id"]
    assert run["topic"] == "binary search"
    assert run["status"] == "completed"
    # run_id propagated through every layer — this is the single cross-layer correlation check.
    assert run["runId"] == run_id
    assert run["kcCount"] == len(created["graph"]["nodes"])
    assert run["moduleCount"] == len(created["modules"])
    assert "createdAt" in run and "updatedAt" in run
    # No snake_case internal ever leaks over the wire — forward-safe across new CourseRun fields.
    leaked = [key for key in run if "_" in key]
    assert not leaked, f"snake_case key leaked over the wire: {leaked}"


async def test_runs_are_listed_newest_first(client: httpx.AsyncClient) -> None:
    # Arrange
    await client.post("/api/courses", json={"topic": "first"})
    await client.post("/api/courses", json={"topic": "second"})

    # Act
    runs = (await client.get("/api/runs")).json()

    # Assert — most recent build leads
    assert [r["topic"] for r in runs] == ["second", "first"]


async def test_limit_query_param_caps_the_list(client: httpx.AsyncClient) -> None:
    # Arrange
    for topic in ("a", "b", "c"):
        await client.post("/api/courses", json={"topic": topic})

    # Act
    runs = (await client.get("/api/runs", params={"limit": 2})).json()

    # Assert — capped at 2; newest-first ordering is proven in the sibling ordering test.
    assert len(runs) == 2


async def test_limit_below_minimum_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs", params={"limit": 0})

    assert response.status_code == 422  # query-param validation at the boundary


async def test_limit_above_maximum_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs", params={"limit": 201})

    assert response.status_code == 422  # upper bound (le=200) enforced at the boundary
