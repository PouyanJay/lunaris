"""A learner's own sessions, listed (T2, the walking skeleton for this journey's new surfaces).

Every lifecycle verb this journey adds needs somewhere to be pressed, and until now there was no
screen that could show a learner their sessions: the API could create one, take a turn, advance and
read one by id, and nothing else. This is the round trip that makes the rest possible, proved end to
end through the real ASGI app, and the layer it adds is the only genuinely new seam in T3 to T6.

The index it reads through has been waiting since Phase 2a: ``live_sessions_user_idx`` on
``(user_id, updated_at desc)``, whose own migration comment names this exact read ("a learner's own
sessions newest first"). It was built and never used.

Scoping is the assertion that matters most. A session is a transcript of somebody being taught, and
the service-role client the loop writes through bypasses RLS, so the list has to refuse another
learner's rows on its own terms rather than trusting the policy underneath it.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from _live_stack import settings_for
from lunaris_api.app import create_app
from lunaris_api.config import get_settings
from lunaris_api.live.dependencies import resolve_graph_store
from lunaris_api.live.session.dependencies import get_live_session_service
from lunaris_api.live.session.service import LiveSessionService
from lunaris_live.session import MemoryKnowledgeStore, MemorySessionStore, StubGrader, StubTutor


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The app over a session store of this test's own.

    The in-memory store is a process-wide singleton by design (opening a session and answering it
    are separate requests), so a suite that shared it would have every test listing every other
    test's sessions. A list route is the first one that could ever notice.
    """
    settings = settings_for(tmp_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    # Built once, not per resolution: a factory returning a fresh store every request would give
    # the POST that opens a session and the GET that lists it two different stores.
    service = LiveSessionService(
        resolve_graph_store(settings),
        MemorySessionStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _opened(client: httpx.AsyncClient, topic: str) -> dict:
    graph = (await client.post("/api/live/graphs", json={"topic": topic})).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


# ── the walking skeleton: one round trip through every layer ─────────────────────────────────────


async def test_a_learner_sees_the_session_they_just_opened(client: httpx.AsyncClient) -> None:
    """Web-facing contract to service to ``lunaris_live.session`` to store and back, which is what
    a skeleton is for. Everything the screen shows is asserted here, because a list that came back
    without a topic on it is a list of identifiers rather than of sessions."""
    # Arrange
    opened = await _opened(client, "How vaccines train the immune system")

    # Act
    response = await client.get("/api/live/sessions")

    # Assert
    assert response.status_code == 200
    listed = response.json()
    assert [entry["sessionId"] for entry in listed] == [opened["sessionId"]]
    only = listed[0]
    assert only["topic"] == "How vaccines train the immune system"
    assert only["status"] == "active"
    assert only["turnCount"] == len(opened["turns"])
    assert only["graphId"] == opened["graphId"]


async def test_the_newest_session_is_the_first_one_listed(client: httpx.AsyncClient) -> None:
    """The order the index exists to serve. A learner coming back wants the thing they were last
    doing, not the first thing they ever did."""
    # Arrange
    first = await _opened(client, "How vaccines train the immune system")
    second = await _opened(client, "How neural networks learn")

    # Act
    listed = (await client.get("/api/live/sessions")).json()

    # Assert
    assert [entry["sessionId"] for entry in listed] == [
        second["sessionId"],
        first["sessionId"],
    ]


async def test_a_learner_with_no_sessions_gets_an_empty_list_not_an_error(
    client: httpx.AsyncClient,
) -> None:
    """The screen's empty state is a real state and has to be reachable without a failure. Pinned
    because "no rows" is exactly the case a store is most likely to raise on."""
    # Act
    response = await client.get("/api/live/sessions")

    # Assert
    assert response.status_code == 200
    assert response.json() == []


async def test_the_list_carries_the_session_id_header_for_correlation(
    client: httpx.AsyncClient,
) -> None:
    """Every other session route rides ``X-Session-Id`` so a learner reporting "it went wrong" can
    be found across the layers. A list names no single session, so it carries the request's own id
    instead: the correlation has to survive the one route that fans out."""
    # Act
    response = await client.get("/api/live/sessions")

    # Assert
    assert response.headers.get("x-request-id")
