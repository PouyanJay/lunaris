"""C1 at the HTTP edge: growing a map for something asked mid-session.

The stub compiler backs these (the suite runs `pipeline="stub"`), so what is proven here is the
endpoint's own contract — that an extension reaches the stored graph, comes back versioned, and that
every way it can fail says something a session could act on.
"""

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
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _compiled(client: httpx.AsyncClient) -> dict:
    return (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()


async def test_a_request_the_map_does_not_cover_grows_it(client: httpx.AsyncClient) -> None:
    # Arrange
    graph = await _compiled(client)

    # Act
    response = await client.post(
        f"/api/live/graphs/{graph['graphId']}/extend",
        json={"request": "How do I pick one for my project?", "anchors": [graph["topoOrder"][0]]},
    )

    # Assert — a bigger map, a new version, and a record of why it differs.
    assert response.status_code == 200, response.text
    extended = response.json()
    assert extended["version"] == graph["version"] + 1
    assert len(extended["nodes"]) > len(graph["nodes"])
    assert extended["edits"][0]["request"] == "How do I pick one for my project?"
    assert any(node["provenance"] == "extended" for node in extended["nodes"])


async def test_the_grown_map_is_what_a_later_read_returns(client: httpx.AsyncClient) -> None:
    """The extension has to be durable — a session that re-opens the map must see the concept it
    asked for, not the version from before it asked."""
    # Arrange
    graph = await _compiled(client)
    await client.post(
        f"/api/live/graphs/{graph['graphId']}/extend", json={"request": "what about momentum"}
    )

    # Act
    reread = (await client.get(f"/api/live/graphs/{graph['graphId']}")).json()

    # Assert
    assert reread["version"] == 2
    assert len(reread["edits"]) == 1


async def test_extending_an_unknown_graph_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/live/graphs/never-compiled/extend", json={"request": "anything"}
    )

    assert response.status_code == 404


@pytest.mark.parametrize("request_text", ["", "   ", "x" * 501])
async def test_an_unusable_request_is_rejected(
    client: httpx.AsyncClient, request_text: str
) -> None:
    # Arrange
    graph = await _compiled(client)

    # Act
    response = await client.post(
        f"/api/live/graphs/{graph['graphId']}/extend", json={"request": request_text}
    )

    # Assert
    assert response.status_code == 422


async def test_an_extension_that_lost_a_race_is_a_conflict(tmp_path: Path) -> None:
    """Two turns of one session can overlap. The loser must be told, so the caller can re-read and
    decide again with the newer map — never silently overwrite the winner."""
    # Arrange — a store that reports the graph moved on underneath us.
    from lunaris_api.live.dependencies import get_live_graph_service
    from lunaris_api.live.service import LiveGraphService
    from lunaris_live.graph import (
        GraphVersionConflictError,
        MemoryGraphStore,
        StubGraphCompiler,
    )

    class RacingStore(MemoryGraphStore):
        def save(self, graph, *, owner_id=None, expected_version=None):
            if expected_version is not None:
                raise GraphVersionConflictError(graph.graph_id)
            super().save(graph, owner_id=owner_id)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    service = LiveGraphService(StubGraphCompiler(), RacingStore())
    app.dependency_overrides[get_live_graph_service] = lambda: service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        graph = (await http_client.post("/api/live/graphs", json={"topic": "Tides"})).json()

        # Act
        response = await http_client.post(
            f"/api/live/graphs/{graph['graphId']}/extend",
            json={"request": "what about spring tides"},
        )

    # Assert
    assert response.status_code == 409
    assert "changed" in response.json()["detail"].lower()
    assert response.headers["X-Run-Id"]


async def _app_with(compiler: object, tmp_path: Path):
    from lunaris_api.live.dependencies import get_live_graph_service
    from lunaris_api.live.service import LiveGraphService
    from lunaris_live.graph import MemoryGraphStore, StubGraphCompiler

    store = MemoryGraphStore()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    # Compile with the real stub so a graph exists, then swap in the failing compiler for extend.
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(
        StubGraphCompiler(), store
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        graph = (await http_client.post("/api/live/graphs", json={"topic": "Tides"})).json()
    app.dependency_overrides[get_live_graph_service] = lambda: LiveGraphService(compiler, store)
    return app, graph


async def test_an_extension_the_model_cannot_answer_is_an_upstream_failure(tmp_path: Path) -> None:
    """Same distinction the compile endpoint draws: nothing usable came back, so say so rather
    than returning the unchanged map as though the question had been handled."""
    # Arrange
    from lunaris_live.graph import GraphCompilationError

    class BarrenCompiler:
        async def compile(self, *args: object, **kwargs: object) -> object:
            raise NotImplementedError

        async def extend(self, *args: object, **kwargs: object) -> object:
            raise GraphCompilationError("nothing new to add")

    app, graph = await _app_with(BarrenCompiler(), tmp_path)

    # Act
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            f"/api/live/graphs/{graph['graphId']}/extend", json={"request": "asdfgh"}
        )

    # Assert
    assert response.status_code == 502
    assert response.headers["X-Run-Id"]


async def test_an_extension_that_overruns_the_pause_is_a_timeout(tmp_path: Path) -> None:
    # Arrange
    class StalledCompiler:
        async def compile(self, *args: object, **kwargs: object) -> object:
            raise NotImplementedError

        async def extend(self, *args: object, **kwargs: object) -> object:
            raise TimeoutError

    app, graph = await _app_with(StalledCompiler(), tmp_path)

    # Act
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        response = await http_client.post(
            f"/api/live/graphs/{graph['graphId']}/extend", json={"request": "anything"}
        )

    # Assert — 504, distinct from the 502 above: the question was fine, the wait was not.
    assert response.status_code == 504
    assert response.headers["X-Run-Id"]
