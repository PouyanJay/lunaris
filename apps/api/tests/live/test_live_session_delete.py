"""Deleting a session, and the line between deleting and forgetting (T4).

Until now the only way to remove a Live session was to delete the auth user and let the cascade take
it. Everything a learner typed lived for ever, and there was no verb to say otherwise. That is a
privacy answer owed to anyone the product is pointed at, not a nicety.

**Delete removes the transcript and nothing else (U2, decided with the user).** Beliefs live in
`live_knowledge`, keyed `(user_id, graph_id, node_id)` with no session id anywhere in it, so a
delete that tried to unpick "what this session taught them" would be guessing. The two are separate
verbs on purpose: this one is "stop keeping what I said", and resetting a topic (T5) is "forget what
you concluded about me". Collapsing them would make one of the two do something the learner did not
ask for, and both are the kind of thing nobody wants done approximately.
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
from lunaris_api.live.session.throttle import LiveSessionThrottle
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
    """The app over stores this test holds, so it can see what a delete did and did not touch."""
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


async def _opened(client: httpx.AsyncClient, topic: str = "How neural networks learn") -> dict:
    graph = (await client.post("/api/live/graphs", json={"topic": topic})).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


# ── the transcript goes ──────────────────────────────────────────────────────────────────────────


async def test_a_deleted_session_is_gone(client: httpx.AsyncClient) -> None:
    """The whole point of the verb. Anything short of the row actually being unreadable afterwards
    is a delete button that files things away rather than removing them."""
    # Arrange
    opened = await _opened(client)

    # Act
    deleted = await client.delete(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    assert deleted.status_code == 204
    assert (await client.get(f"/api/live/sessions/{opened['sessionId']}")).status_code == 404


async def test_a_deleted_session_leaves_the_list(client: httpx.AsyncClient) -> None:
    """The screen it is deleted from has to agree with the store. A row that survived the list
    would be a session a learner believes they removed and can still be shown."""
    # Arrange
    kept = await _opened(client, "How vaccines train the immune system")
    doomed = await _opened(client, "How neural networks learn")

    # Act
    await client.delete(f"/api/live/sessions/{doomed['sessionId']}")

    # Assert
    listed = (await client.get("/api/live/sessions")).json()
    assert [entry["sessionId"] for entry in listed] == [kept["sessionId"]]


async def test_deleting_a_session_that_is_not_there_is_not_found(
    client: httpx.AsyncClient,
) -> None:
    """404, the posture every session route holds: the existence of a session is itself
    owner-scoped information, so "no such session" and "not yours" must be one answer."""
    # Act
    response = await client.delete("/api/live/sessions/nope")

    # Assert
    assert response.status_code == 404


# ── what a delete must NOT take with it (U2) ─────────────────────────────────────────────────────


async def test_deleting_a_session_keeps_what_the_learner_demonstrated(
    client: httpx.AsyncClient, knowledge: MemoryKnowledgeStore
) -> None:
    """The decision this task turns on. Deleting a transcript is "stop keeping what I said", not
    "forget what you concluded about me" — and the second is T5's separate, explicit verb. A learner
    tidying up their history must not silently lose the progress that history earned them."""
    # Arrange: a session with an answer in it, so there is a belief to keep.
    opened = await _opened(client)
    await client.post(
        f"/api/live/sessions/{opened['sessionId']}/turns",
        json={"answer": "It adjusts numbers when it gets one wrong.", "answeringSeq": 1},
    )
    before = knowledge.load(opened["graphId"])
    assert before.nodes, "the arrangement is pointless if the answer moved no belief"

    # Act
    await client.delete(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    after = knowledge.load(opened["graphId"])
    assert after.nodes == before.nodes


async def test_deleting_a_session_keeps_the_map_it_walked(client: httpx.AsyncClient) -> None:
    """A map outlives every sitting on it. Deleting one learner's session must not take away the
    compiled graph, which another session (and another learner) may be walking right now."""
    # Arrange
    opened = await _opened(client)

    # Act
    await client.delete(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    assert (await client.get(f"/api/live/graphs/{opened['graphId']}")).status_code == 200


# ── deleting while a turn is in flight ───────────────────────────────────────────────────────────


async def test_a_delete_cannot_land_while_a_turn_is_being_taken(tmp_path: Path) -> None:
    """A rendezvous, never a sleep.

    The store's save is an upsert on the id, so a turn that landed after a delete would write the
    row straight back: a learner's deleted transcript, resurrected by a call that was already in
    flight when they pressed the button. The slot makes deleting and teaching mutually exclusive,
    the same guard a discard needs and for the same reason.
    """

    class HeldTutor(StubTutor):
        """The stub tutor, held at the door until the test lets it through."""

        def __init__(self) -> None:
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def teach(self, *args: object, **kwargs: object) -> str:
            self.entered.set()
            await asyncio.wait_for(self.release.wait(), 5)
            return await super().teach(*args, **kwargs)  # type: ignore[arg-type]

    settings = settings_for(tmp_path)
    tutor = HeldTutor()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    service = LiveSessionService(
        resolve_graph_store(settings),
        MemorySessionStore(),
        knowledge=MemoryKnowledgeStore(),
        tutor=tutor,
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
        throttle=LiveSessionThrottle(open_daily_cap=0),
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Arrange: a turn held open inside the tutor. Both flags reset AFTER the open, because
        # opening a session teaches a turn too and a signal left set from it would let the wait
        # below return before the answer had claimed anything.
        tutor.release.set()
        opened = await _opened(client)
        tutor.release.clear()
        tutor.entered.clear()
        answering = asyncio.create_task(
            client.post(
                f"/api/live/sessions/{opened['sessionId']}/turns",
                json={"answer": "A guess.", "answeringSeq": opened["turns"][-1]["seq"]},
            )
        )
        await asyncio.wait_for(tutor.entered.wait(), 5)

        # Act
        refused = await client.delete(f"/api/live/sessions/{opened['sessionId']}")

        # Assert
        assert refused.status_code == 409
        tutor.release.set()
        assert (await answering).status_code == 200
        assert (await client.get(f"/api/live/sessions/{opened['sessionId']}")).status_code == 200
