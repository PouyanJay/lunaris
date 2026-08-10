"""Lunaris Live, Phase 2a — the walking skeleton, end to end through the API.

A learner opens a session on a compiled graph, the session is persisted, and it comes back with its
first turn. Nothing here asserts *teaching*: the director is a stub that always opens on the map's
first concept and the tutor's words are a fixed string. What this pins is that the whole path is
wired — web-facing contract → service → ``lunaris_live.session`` → store — with one ``session_id``
correlating the lot, and that a session is a row rather than connection state (U2), so a reload
returns the learner to where they were.

Exercised through the real ASGI app over httpx; the only stub is the compiler behind the graph the
session runs on.
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


async def _graph(client: httpx.AsyncClient) -> dict:
    """A compiled map for the session to run on — Phase 1's surface, used as given."""
    return (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()


async def test_opening_a_session_returns_its_first_turn(client: httpx.AsyncClient) -> None:
    # Arrange
    graph = await _graph(client)

    # Act
    response = await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})

    # Assert — the contract the surface renders: a live session, on a known map, already teaching.
    assert response.status_code == 201, response.text
    session = response.json()
    assert session["graphId"] == graph["graphId"]
    assert session["status"] == "active"
    assert session["turns"], "a session that opens with nothing to show is a loading spinner"

    first = session["turns"][0]
    assert first["seq"] == 1
    # Every turn is a director move plus what the tutor said about it (A2). The move is what makes
    # the transcript auditable — without it a turn is prose nobody can explain the choice of.
    assert first["move"]["kind"] == "introduce"
    assert first["move"]["nodeId"] in {node["id"] for node in graph["nodes"]}
    assert first["move"]["reason"], "a move with no reason cannot be audited (plan §7)"
    assert first["tutor"].strip()

    # The run id has to ride the response: a session is many minutes of work across many turns, and
    # a learner reporting "it went wrong" needs to name it.
    assert response.headers["X-Session-Id"] == session["sessionId"]


async def test_the_first_concept_is_one_with_nothing_before_it(client: httpx.AsyncClient) -> None:
    """Even a stub director may not open in the middle of the map. The whole point of Phase 1's
    ordering is that a learner is never shown a concept whose prerequisites they have not met."""
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert
    opened_on = session["turns"][0]["move"]["nodeId"]
    node = next(n for n in graph["nodes"] if n["id"] == opened_on)
    assert node["requires"] == [], f"{opened_on} was taught before its prerequisites"


async def test_a_session_is_a_row_not_a_connection(client: httpx.AsyncClient) -> None:
    """U2: a 25-40 minute session that dies on a refresh cannot be tested end to end, and Phase 1
    already learned this shape once when a dropped stream nearly cancelled its compile (AD12)."""
    # Arrange
    graph = await _graph(client)
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Act — a second request, the way a reloaded tab re-opens the session it was in.
    response = await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Assert — the same session, at the same turn, not a fresh one.
    assert response.status_code == 200, response.text
    resumed = response.json()
    assert resumed["sessionId"] == opened["sessionId"]
    assert resumed["turns"] == opened["turns"]


async def test_a_session_on_a_map_that_is_not_there_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    # Act
    response = await client.post("/api/live/sessions", json={"graphId": "no-such-map"})

    # Assert — and the id rides the failure. A header set only once the work succeeded would be
    # absent from exactly the responses somebody needs to report, which is the whole point of it.
    assert response.status_code == 404
    assert response.headers["X-Session-Id"]


async def test_another_owners_session_is_not_found(client: httpx.AsyncClient) -> None:
    """A session's existence is owner-scoped information, so a stranger gets 404 rather than 403 —
    the same posture Phase 1 took for graphs."""
    assert (await client.get("/api/live/sessions/no-such-session")).status_code == 404
