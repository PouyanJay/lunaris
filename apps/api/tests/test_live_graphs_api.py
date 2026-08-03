"""Lunaris Live, Phase 1 — the walking skeleton, end to end through the API.

A topic goes in at the HTTP edge, Live's compiler produces a concept graph, the graph is persisted,
and it is re-readable by id. Nothing here asserts *good* curriculum — the compiler under test is the
stub, and real decomposition is T3. What this suite pins is that the whole path is wired: web-facing
contract → service → ``lunaris_live`` package → store, with one ``run_id`` correlating the lot.

The API is exercised through the real ASGI app over httpx (no mocked service), so a break anywhere
in that chain fails here rather than in production.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
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


async def test_compiling_a_topic_returns_a_concept_graph(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})

    # Assert — the contract the web renders: a graph carrying its topic and its concepts.
    assert response.status_code == 201, response.text
    graph = response.json()
    assert graph["topic"] == "How neural networks learn"
    assert graph["version"] == 1
    assert len(graph["nodes"]) >= 2, "a walking skeleton still has to produce a real graph shape"

    # Every node is teachable-shaped: it can be named and defined, and it says what it needs first.
    for node in graph["nodes"]:
        assert node["id"] and node["name"] and node["definition"]
        assert isinstance(node["requires"], list)

    # Provenance is structural — a cold compile marks its nodes as such (C1 later adds "extended").
    assert {node["provenance"] for node in graph["nodes"]} == {"compiled"}


async def test_the_graph_is_a_dag_in_dependency_order(client: httpx.AsyncClient) -> None:
    # Act
    response = await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})

    # Assert — the correctness moat, which does not weaken because the compiler is a stub: the
    # graph is acyclic and its topological order really does place prerequisites first.
    graph = response.json()
    assert graph["isAcyclic"] is True

    order = graph["topoOrder"]
    assert sorted(order) == sorted(node["id"] for node in graph["nodes"])
    for node in graph["nodes"]:
        for prerequisite in node["requires"]:
            assert order.index(prerequisite) < order.index(node["id"])


async def test_a_compiled_graph_is_persisted_and_re_readable(client: httpx.AsyncClient) -> None:
    # Arrange
    compiled = (await client.post("/api/live/graphs", json={"topic": "Photosynthesis"})).json()

    # Act — a second request, the way the web re-opens a map it already compiled.
    response = await client.get(f"/api/live/graphs/{compiled['graphId']}")

    # Assert — the graph survived the round trip through the store, not just the response.
    assert response.status_code == 200, response.text
    assert response.json() == compiled


async def test_an_unknown_graph_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/live/graphs/does-not-exist")

    assert response.status_code == 404


async def test_the_compile_is_correlated_by_one_run_id(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    # Act
    response = await client.post("/api/live/graphs", json={"topic": "Tides"})

    # Assert — the run id is handed to the caller for cross-layer triangulation ...
    run_id = response.headers["X-Run-Id"]
    assert run_id

    # ... and the compile really logged under it at every layer it crossed. Read off the stdout JSON
    # rather than structlog's capture_logs, which can't intercept a module logger another test has
    # already cached against the real pipeline (house pattern — see test_run_event_recorder.py).
    correlated = [line for line in _json_log_lines(capsys) if line.get("run_id") == run_id]
    events = {line.get("event") for line in correlated}
    assert {
        "live.graph.compile_started",  # the API service
        "live.graph.compiled",  # inside the lunaris_live package
        # Passes no run_id of its own — it can only appear here if the contextvars binding
        # propagated, which is what stops this suite from passing with bind_run_id deleted and the
        # id merely threaded through function arguments by hand.
        "live.graph.compile_finished",
    } <= events, f"run {run_id} was not traceable across the layers; saw {events}"


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


@pytest.mark.parametrize("topic", ["", "   ", "x" * 201])
async def test_an_unusable_topic_is_rejected(client: httpx.AsyncClient, topic: str) -> None:
    """Blank and over-long topics are refused at the trust boundary, not compiled."""
    response = await client.post("/api/live/graphs", json={"topic": topic})

    assert response.status_code == 422


async def test_a_topic_at_the_length_limit_is_accepted(client: httpx.AsyncClient) -> None:
    """The boundary itself, not just past it — an off-by-one in the constraint would reject a
    legitimate topic, and only a test on the exact limit catches that."""
    response = await client.post("/api/live/graphs", json={"topic": "x" * 200})

    assert response.status_code == 201, response.text
