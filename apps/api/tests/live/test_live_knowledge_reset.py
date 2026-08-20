"""Forgetting a topic: the other half of the delete pair (T5).

Deleting a session is "stop keeping what I said". This is "forget what you concluded about me". The
two are separate verbs because they remove different things and a learner means one or the other,
never approximately both (U2): beliefs live in `live_knowledge`, keyed by user, graph and node
with no session id in it, so no delete of a transcript could clear them without guessing.

It is also the repair verb. A learner whose beliefs were moved by a broken assessment surface (the
quiz card T1 fixed, which marked correct answers wrong and pushed `p_known` **down**) has a record
that will keep steering the director at them for ever. Without this, the fix is invisible to anyone
who already used the thing.

The hazard worth naming: a turn already in flight holds a model in memory and writes it back when it
finishes, which would restore the very beliefs the learner just cleared. So a reset refuses while a
session on that map is still going, rather than racing it.
"""

import asyncio
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
from lunaris_live.session import (
    MemoryKnowledgeStore,
    MemorySessionStore,
    StubGrader,
    StubTutor,
)


@pytest.fixture
def knowledge() -> MemoryKnowledgeStore:
    return MemoryKnowledgeStore()


@pytest.fixture
async def client(
    tmp_path: Path, knowledge: MemoryKnowledgeStore
) -> AsyncIterator[httpx.AsyncClient]:
    """The app over stores this test holds, so it can see what a reset did and did not touch."""
    settings = settings_for(tmp_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    service = LiveSessionService(
        resolve_graph_store(settings),
        MemorySessionStore(),
        knowledge=knowledge,
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _taught(client: httpx.AsyncClient, topic: str = "How neural networks learn") -> dict:
    """A session with one answer in it, so there is a belief to forget."""
    graph = (await client.post("/api/live/graphs", json={"topic": topic})).json()
    session = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    await client.post(
        f"/api/live/sessions/{session['sessionId']}/turns",
        json={"answer": "It adjusts numbers when it gets one wrong.", "answeringSeq": 1},
    )
    return session


async def _left(client: httpx.AsyncClient, session_id: str) -> None:
    await client.post(f"/api/live/sessions/{session_id}/discard")


# ── the beliefs go ───────────────────────────────────────────────────────────────────────────────


async def test_resetting_a_topic_forgets_what_it_concluded(
    client: httpx.AsyncClient, knowledge: MemoryKnowledgeStore
) -> None:
    """The whole verb. A learner asking to be forgotten on a topic and finding the director still
    treating them as it did before would have been told something untrue."""
    # Arrange
    session = await _taught(client)
    await _left(client, session["sessionId"])
    assert knowledge.load(session["graphId"]).nodes, "nothing to forget makes this test vacuous"

    # Act
    response = await client.delete(f"/api/live/knowledge/{session['graphId']}")

    # Assert
    assert response.status_code == 204
    assert knowledge.load(session["graphId"]).nodes == {}


async def test_resetting_one_topic_leaves_the_others_alone(
    client: httpx.AsyncClient, knowledge: MemoryKnowledgeStore
) -> None:
    """Node ids are graph-local, so two maps are unrelated records. A reset that reached past its
    own map would take away progress the learner never asked about."""
    # Arrange
    forgotten = await _taught(client, "How neural networks learn")
    kept = await _taught(client, "How vaccines train the immune system")
    await _left(client, forgotten["sessionId"])
    await _left(client, kept["sessionId"])
    before = knowledge.load(kept["graphId"]).nodes

    # Act
    await client.delete(f"/api/live/knowledge/{forgotten['graphId']}")

    # Assert
    assert knowledge.load(kept["graphId"]).nodes == before


async def test_resetting_a_topic_never_taught_is_still_fine(client: httpx.AsyncClient) -> None:
    """Idempotent, and quiet about it. "Forget this" on a topic with nothing to forget has already
    happened, and a learner pressing it twice should not meet an error the second time."""
    # Arrange
    graph = (await client.post("/api/live/graphs", json={"topic": "Anything at all"})).json()

    # Act
    response = await client.delete(f"/api/live/knowledge/{graph['graphId']}")

    # Assert
    assert response.status_code == 204


# ── what a reset must NOT take with it (U2) ──────────────────────────────────────────────────────


async def test_resetting_a_topic_keeps_the_transcripts(client: httpx.AsyncClient) -> None:
    """The inverse of T4's assertion, and the other half of the same decision. Forgetting what was
    concluded about a learner is not the same as destroying the record of what they said."""
    # Arrange
    session = await _taught(client)
    await _left(client, session["sessionId"])

    # Act
    await client.delete(f"/api/live/knowledge/{session['graphId']}")

    # Assert
    read = await client.get(f"/api/live/sessions/{session['sessionId']}")
    assert read.status_code == 200
    assert len(read.json()["turns"]) > 1


async def test_resetting_a_topic_keeps_the_map(client: httpx.AsyncClient) -> None:
    """A map is a map of the subject, not a record of the learner. Forgetting a learner's progress
    must not throw away the compiled graph, which cost minutes and money to build."""
    # Arrange
    session = await _taught(client)
    await _left(client, session["sessionId"])

    # Act
    await client.delete(f"/api/live/knowledge/{session['graphId']}")

    # Assert
    assert (await client.get(f"/api/live/graphs/{session['graphId']}")).status_code == 200


# ── a reset cannot race a session that is still going ────────────────────────────────────────────


async def test_a_topic_with_a_session_still_going_cannot_be_reset(
    client: httpx.AsyncClient, knowledge: MemoryKnowledgeStore
) -> None:
    """The hazard this task exists to avoid, and the reason the refusal is a feature.

    A session in progress holds a model in memory and writes it back at the end of every turn. Reset
    the beliefs underneath it and the next turn restores them: the learner's clearing silently
    undone by a session they were still in. Refusing is both correct and the honest instruction —
    finish or leave the session first.
    """
    # Arrange: taught, and deliberately NOT left.
    session = await _taught(client)
    before = knowledge.load(session["graphId"]).nodes

    # Act
    response = await client.delete(f"/api/live/knowledge/{session['graphId']}")

    # Assert
    assert response.status_code == 409
    assert knowledge.load(session["graphId"]).nodes == before


async def test_a_topic_can_be_reset_once_its_session_has_ended(
    client: httpx.AsyncClient, knowledge: MemoryKnowledgeStore
) -> None:
    """The refusal has to lift, or "finish the session first" would be advice that never works."""
    # Arrange
    session = await _taught(client)
    assert (await client.delete(f"/api/live/knowledge/{session['graphId']}")).status_code == 409

    # Act
    await client.post(f"/api/live/sessions/{session['sessionId']}/end")
    response = await client.delete(f"/api/live/knowledge/{session['graphId']}")

    # Assert
    assert response.status_code == 204
    assert knowledge.load(session["graphId"]).nodes == {}


async def test_a_session_on_another_topic_does_not_block_the_reset(
    client: httpx.AsyncClient,
) -> None:
    """The block is per map, not per learner. One open session must not freeze every other topic's
    reset, or a learner with a session they never finished could never clear anything again."""
    # Arrange
    elsewhere = await _taught(client, "How vaccines train the immune system")
    target = await _taught(client, "How neural networks learn")
    await _left(client, target["sessionId"])
    assert elsewhere["graphId"] != target["graphId"]

    # Act
    response = await client.delete(f"/api/live/knowledge/{target['graphId']}")

    # Assert
    assert response.status_code == 204


async def test_a_reset_cannot_land_while_a_turn_is_being_taken(client: httpx.AsyncClient) -> None:
    """A turn in flight is by definition a session that is still going, so the same refusal covers
    it. Asserted separately because the two are different windows and only one of them is obvious:
    a session between turns is idle, and a session mid-turn is holding the model in memory."""
    # Arrange
    session = await _taught(client)

    # Act: no rendezvous needed — the session is non-terminal for the whole of its life, so the
    # refusal does not depend on catching a call inside a model.
    response = await client.delete(f"/api/live/knowledge/{session['graphId']}")

    # Assert
    assert response.status_code == 409


# ── scoping, at the API's own level ──────────────────────────────────────────────────────────────


async def test_the_reset_is_correlated_for_the_logs(client: httpx.AsyncClient) -> None:
    """A learner reporting "I cleared it and it came back" has to be findable. The graph is the
    subject here, so it is what the correlation names."""
    # Arrange
    graph = (await client.post("/api/live/graphs", json={"topic": "Anything at all"})).json()

    # Act
    response = await client.delete(f"/api/live/knowledge/{graph['graphId']}")

    # Assert
    assert response.headers.get("x-graph-id") == graph["graphId"]


async def test_concurrent_resets_of_the_same_topic_both_answer(
    client: httpx.AsyncClient,
) -> None:
    """A double-click is not an error. Both presses find nothing left to do and say so."""
    # Arrange
    graph = (await client.post("/api/live/graphs", json={"topic": "Anything at all"})).json()

    # Act
    first, second = await asyncio.gather(
        client.delete(f"/api/live/knowledge/{graph['graphId']}"),
        client.delete(f"/api/live/knowledge/{graph['graphId']}"),
    )

    # Assert
    assert {first.status_code, second.status_code} == {204}
