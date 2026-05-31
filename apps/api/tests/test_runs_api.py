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


async def test_runs_list_is_empty_before_any_build(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/runs")

    assert response.status_code == 200
    assert response.json() == []


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
