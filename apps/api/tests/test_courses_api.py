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
        pipeline="stub", course_dir=tmp_path, cors_origins=()
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
