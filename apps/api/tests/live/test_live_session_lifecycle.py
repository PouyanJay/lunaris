"""Ending a session on purpose, and walking away from one (T3).

Until now a session had no way to stop. The director closed it when the clock ran out or when there
was nothing left worth teaching, and a learner who wanted to leave could only shut the tab, which
left the row `active` for ever holding a transcript nobody would come back to. The first real
browser session hit exactly this: the learner asked how to stop and there was no verb to answer
with.

Two verbs, because they are two different things a learner means:

* **End** is finishing. It runs the close ceremony the director would have run, so the learner gets
  the recap, the mastery delta and the day to come back. It costs a model call, and it is worth one.
* **Discard** is leaving. Nothing is recapped, nothing is scheduled, no model is called. The session
  is marked abandoned, which is its own status precisely so that a session that ended *well* and one
  somebody walked out of are never counted as the same thing.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
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
    DirectorMove,
    MemoryKnowledgeStore,
    MemorySessionStore,
    MoveKind,
    Session,
    SessionStatus,
    SessionTurn,
    StubGrader,
    StubTutor,
)


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    """The app over a session store of this test's own (the singleton lesson from T2)."""
    settings = settings_for(tmp_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
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


async def _opened(client: httpx.AsyncClient, topic: str = "How neural networks learn") -> dict:
    graph = (await client.post("/api/live/graphs", json={"topic": topic})).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


# ── ending: the ceremony, on demand ──────────────────────────────────────────────────────────────


async def test_ending_a_session_closes_it_with_its_ceremony(client: httpx.AsyncClient) -> None:
    """The same ending the clock would have produced, asked for rather than waited for. A stop
    button that just marked the row closed would take the recap away from the learner who chose to
    stop and give it only to the one who ran out of time."""
    # Arrange
    opened = await _opened(client)

    # Act
    response = await client.post(f"/api/live/sessions/{opened['sessionId']}/end")

    # Assert
    assert response.status_code == 200
    ended = response.json()
    assert ended["status"] == "closed"
    # The ceremony is a turn, and it is the last one: the meter the learner reads is on it.
    closing = ended["turns"][-1]
    assert closing["move"]["kind"] == "close"
    assert closing["surface"]["kind"] == "mastery_meter"


async def test_the_close_says_the_learner_asked_for_it(client: httpx.AsyncClient) -> None:
    """The director's reason is read by a human auditing a session. A close a learner chose and a
    close the clock forced must not read identically, or the trace loses the only thing that tells
    them apart."""
    # Arrange
    opened = await _opened(client)

    # Act
    ended = (await client.post(f"/api/live/sessions/{opened['sessionId']}/end")).json()

    # Assert
    assert "asked" in ended["turns"][-1]["move"]["reason"].lower()


async def test_ending_a_session_twice_does_not_run_the_ceremony_twice(
    client: httpx.AsyncClient,
) -> None:
    """A stop button is a thing people double-click, and this one costs a model call. The second
    press returns the session that already ended rather than paying for a second goodbye."""
    # Arrange
    opened = await _opened(client)
    first = (await client.post(f"/api/live/sessions/{opened['sessionId']}/end")).json()

    # Act
    second = await client.post(f"/api/live/sessions/{opened['sessionId']}/end")

    # Assert
    assert second.status_code == 200
    assert len(second.json()["turns"]) == len(first["turns"])


# ── discarding: leaving, without a ceremony ──────────────────────────────────────────────────────


async def test_discarding_a_session_abandons_it(client: httpx.AsyncClient) -> None:
    """Its own status, never `closed`. A session somebody walked out of and one that ended well are
    different facts about a learner, and collapsing them would make every count of "sessions
    completed" a lie."""
    # Arrange
    opened = await _opened(client)

    # Act
    response = await client.post(f"/api/live/sessions/{opened['sessionId']}/discard")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "abandoned"


async def test_discarding_adds_no_turn_and_asks_no_model(client: httpx.AsyncClient) -> None:
    """Leaving is not a teaching moment. A learner who wants out gets out, at no cost and with no
    words written at them on the way."""
    # Arrange
    opened = await _opened(client)

    # Act
    discarded = (await client.post(f"/api/live/sessions/{opened['sessionId']}/discard")).json()

    # Assert
    assert len(discarded["turns"]) == len(opened["turns"])


async def test_an_abandoned_session_cannot_be_answered(client: httpx.AsyncClient) -> None:
    """Walking away has to mean something. A session that still took turns after being discarded
    would be a stop button that stopped nothing."""
    # Arrange
    opened = await _opened(client)
    await client.post(f"/api/live/sessions/{opened['sessionId']}/discard")

    # Act
    response = await client.post(
        f"/api/live/sessions/{opened['sessionId']}/turns",
        json={"answer": "Still here.", "answeringSeq": opened["turns"][-1]["seq"]},
    )

    # Assert
    assert response.status_code == 409


async def test_a_discarded_session_is_still_the_learner_s_to_read(
    client: httpx.AsyncClient,
) -> None:
    """Discard is not delete (U2). The transcript survives until the learner says otherwise, which
    is what makes deleting it a separate and deliberate act rather than a side effect of leaving."""
    # Arrange
    opened = await _opened(client)
    await client.post(f"/api/live/sessions/{opened['sessionId']}/discard")

    # Act
    response = await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "abandoned"


# ── both verbs, on a session that is not there ───────────────────────────────────────────────────


@pytest.mark.parametrize("verb", ["end", "discard"])
async def test_another_learner_s_session_is_not_found(client: httpx.AsyncClient, verb: str) -> None:
    """404 rather than 403, the posture every session route holds: the existence of a session is
    itself owner-scoped information."""
    # Act
    response = await client.post(f"/api/live/sessions/nope/{verb}")

    # Assert
    assert response.status_code == 404


# ── leaving while a turn is in flight ────────────────────────────────────────────────────────────


async def test_a_discard_cannot_land_while_a_turn_is_being_taken(tmp_path: Path) -> None:
    """A rendezvous, never a sleep: the discard is attempted *during* a turn, whatever the machine's
    speed.

    A discard writes unconditionally, because there is no answer for it to lose a compare-and-set
    to. So a turn that landed after one would write the session back to ACTIVE and bring a session
    the learner had just left back to life. The slot makes leaving and teaching mutually exclusive,
    and a learner who tries to leave mid-turn is told a turn is in flight rather than being quietly
    ignored.
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
        # Arrange: a session whose next turn is held open inside the tutor.
        tutor.release.set()
        opened = await _opened(client)
        # Both flags reset AFTER the open, because opening a session teaches a turn too: leaving
        # ``entered`` set from it would let the wait below return before the answer had claimed
        # anything, and the test would pass while proving nothing.
        tutor.release.clear()
        tutor.entered.clear()
        answering = asyncio.create_task(
            client.post(
                f"/api/live/sessions/{opened['sessionId']}/turns",
                json={"answer": "A guess.", "answeringSeq": opened["turns"][-1]["seq"]},
            )
        )
        await asyncio.wait_for(tutor.entered.wait(), 5)

        # Act: leave, while that turn is still inside the tutor.
        refused = await client.post(f"/api/live/sessions/{opened['sessionId']}/discard")

        # Assert
        assert refused.status_code == 409
        tutor.release.set()
        assert (await answering).status_code == 200
        # And the session is still the learner's, still active, not half-left.
        after = (await client.get(f"/api/live/sessions/{opened['sessionId']}")).json()
        assert after["status"] == "active"


# ── ending a session that has nothing to end ─────────────────────────────────────────────────────


async def test_ending_a_session_that_never_started_teaching_abandons_it(tmp_path: Path) -> None:
    """A session still being placed has no map, nothing taught, and no meter worth showing: a
    ceremony about nothing is worse than no ceremony. Leaving is the honest ending for it.

    Composed over a store this test holds, so the placing session can be put there directly rather
    than by standing up a whole compile plane, an interviewer and a prior mapper to reach one
    status. What is under test is the ending, not the interview that leads to it.
    """
    # Arrange
    settings = settings_for(tmp_path)
    sessions = MemorySessionStore()
    sessions.save(
        Session(
            session_id="s-placing",
            graph_id="g-pending",
            topic="How vaccines work",
            status=SessionStatus.PLACING,
            started_at=datetime.now(UTC),
            turns=[
                SessionTurn(
                    seq=1,
                    move=DirectorMove(kind=MoveKind.PLACE, reason="Getting to know you."),
                    tutor="What have you come across about this already?",
                    run_id="r1",
                )
            ],
        )
    )
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    service = LiveSessionService(
        resolve_graph_store(settings),
        sessions,
        knowledge=MemoryKnowledgeStore(),
        tutor=StubTutor(),
        grader=StubGrader(),
        session_budget_s=settings.live_session_budget_s,
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Act
        ended = (await client.post("/api/live/sessions/s-placing/end")).json()

        # Assert
        assert ended["status"] == "abandoned"
        # No goodbye written at somebody who was never taught anything.
        assert len(ended["turns"]) == 1
