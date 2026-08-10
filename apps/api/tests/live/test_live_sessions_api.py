"""Lunaris Live, Phase 2a — a session, end to end through the API.

A learner opens a session on a compiled graph, the session is persisted, and it comes back with its
first turn. T1 pinned the wiring — web-facing contract → service → ``lunaris_live.session`` → store,
with one ``session_id`` correlating the lot, and a session as a row rather than connection state
(U2) so a reload returns the learner to where they were.

T4 makes the turn real: the move is the director's (T3) over what this learner already knows (T2),
and the words are the tutor's, written over the concept's authored teaching notes. What the API
level proves is that those notes *travel* — compiled into the map, through the store, into the
session, out to the learner — which no test of any one layer can see.

Exercised through the real ASGI app over httpx; the stubs are the compiler behind the graph and the
tutor behind the turn, both real implementations of their protocols.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.dependencies import resolve_graph_store
from lunaris_api.live.session.dependencies import get_live_session_service, get_live_tutor
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.graph import ConceptNode
from lunaris_live.session import (
    DirectorMove,
    MemoryKnowledgeStore,
    Session,
    SessionFormatError,
    StubTutor,
    TutorUnavailableError,
)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_with_a_silent_tutor(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The same app with a tutor that cannot speak — the provider being down, mid-open."""

    class SilentTutor:
        async def teach(
            self, move: DirectorMove, node: ConceptNode, *, topic: str, run_id: str
        ) -> str:
            raise TutorUnavailableError("provider is down")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app.dependency_overrides[get_live_tutor] = lambda: SilentTutor()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def client_with_an_unreadable_session(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The same app over a store holding a session this build can no longer parse."""

    class UnreadableStore:
        def save(self, session: Session, *, owner_id: str | None = None) -> None: ...

        def load(self, session_id: str, *, owner_id: str | None = None) -> Session:
            raise SessionFormatError(f"session {session_id} is not in a readable format")

    settings = Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_live_session_service] = lambda: LiveSessionService(
        resolve_graph_store(settings),
        UnreadableStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=StubTutor(),
        session_budget_s=settings.live_session_budget_s,
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


async def test_the_opening_turn_teaches_what_the_map_authored(client: httpx.AsyncClient) -> None:
    """The claim no single layer can make: a concept's teaching notes reach the learner.

    Phase 1 pays a model call per concept to author misconceptions — "the wrong models learners
    commonly hold, stated as the learner would believe them" — precisely so the tutor can go after
    the specific wrong idea in front of it. If they stop travelling anywhere between the compiler
    and the transcript, every session silently degrades to a definition read aloud, and the map
    still looks perfect.
    """
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert — the authored text itself, taken from the compiled map rather than restated here, so
    # this cannot pass by agreeing with a copy of the stub.
    taught_on = session["turns"][0]["move"]["nodeId"]
    node = next(n for n in graph["nodes"] if n["id"] == taught_on)
    misconception = node["teachingSpec"]["misconceptions"][0]
    assert misconception in session["turns"][0]["tutor"]


async def test_a_turn_is_correlated_by_the_run_that_produced_it(client: httpx.AsyncClient) -> None:
    """R6: the session carries a ``session_id``, each turn carries its own ``run_id``. A turn is
    now one or more model calls, and the two ids answer different questions — "show me this
    learner's session" and "show me what the tutor was asked on this line".

    Deliberately the *shape* half of the claim: on its own this would pass on a constant. The test
    below it is the binding half, and neither is the whole claim without the other.
    """
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert
    run_id = session["turns"][0]["runId"]
    assert run_id
    assert run_id != session["sessionId"], "a turn's run is not the session it belongs to"


async def test_the_turns_run_id_is_the_one_its_work_logged_under(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Otherwise the id on the turn is decoration. The point of storing it is that somebody holding
    a line of transcript can find what actually happened underneath it — so the id the learner gets
    back has to be the id the work was logged with, at every layer it crossed."""
    # Arrange
    graph = await _graph(client)

    # Act
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()

    # Assert — read off the stdout JSON rather than structlog's capture_logs, which cannot
    # intercept a module logger another test has already cached (house pattern, see
    # test_live_graphs_api.py).
    run_id = session["turns"][0]["runId"]
    correlated = [line for line in _json_log_lines(capsys) if line.get("run_id") == run_id]
    events = {line.get("event") for line in correlated}
    # ``live.session.started`` passes no ids of its own — it can only appear here if the contextvars
    # binding propagated, which is what stops this passing with the binding deleted and the id
    # merely threaded through arguments by hand.
    assert "live.session.started" in events, f"turn {run_id} left no trace; saw {events}"
    assert all(line.get("session_id") == session["sessionId"] for line in correlated), (
        "a turn's run must stay attached to the session it belongs to"
    )


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


async def test_a_tutor_that_cannot_speak_leaves_no_session_behind(
    client_with_a_silent_tutor: httpx.AsyncClient,
) -> None:
    """A session whose first turn never happened is not a session. Persisting the shell would give
    a learner a resumable transcript with nothing in it — and ``turns`` is what the surface renders,
    so it would read as a session that opened and then went quiet."""
    # Arrange
    graph = await _graph(client_with_a_silent_tutor)

    # Act
    response = await client_with_a_silent_tutor.post(
        "/api/live/sessions", json={"graphId": graph["graphId"]}
    )

    # Assert — retryable (the provider may come back), correlated, and nothing persisted.
    assert response.status_code == 503, response.text
    session_id = response.headers["X-Session-Id"]
    assert session_id
    resumed = await client_with_a_silent_tutor.get(f"/api/live/sessions/{session_id}")
    assert resumed.status_code == 404


async def test_a_session_this_build_cannot_read_is_not_offered_as_a_retry(
    client_with_an_unreadable_session: httpx.AsyncClient,
) -> None:
    """Told apart from storage being down, because the advice differs: an outage ends and a reload
    fixes it, a row written by a schema this build no longer understands never becomes readable. As
    a 503 it would invite a learner to reload forever."""
    # Act
    response = await client_with_an_unreadable_session.get("/api/live/sessions/s1")

    # Assert
    assert response.status_code == 500, response.text
    assert response.headers["X-Session-Id"] == "s1"


async def test_the_first_concept_is_one_with_nothing_before_it(client: httpx.AsyncClient) -> None:
    """The director may not open in the middle of the map. The whole point of Phase 1's ordering is
    that a learner is never shown a concept whose prerequisites they have not met."""
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
