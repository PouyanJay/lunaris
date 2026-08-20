"""The 30-minute bound, made real (T6).

A Lunaris Live session is bounded by design (plan §6: 25-40 minutes), and until now that bound was
only ever noticed *from inside a turn*: `SessionClock.is_spent` is read in `decide_move`, which runs
when a learner answers. Walk away and the row stayed `active` for ever. A "bounded session" that
only notices its own bound when somebody acts is not bounded; it is a session that happens to end if
you keep talking to it.

Per U3, the fix is lazy rather than a sweeper: an expired session closes **when something looks at
it**, on a read or in a listing. No new deployed component, nothing that can silently stop running.
The accepted cost is that a session nobody ever revisits keeps its stale status until something
touches it.

The close that a look performs is **deterministic and free**. A GET that spent money on a tutor call
would be a surprising thing for a page load to do, so the ceremony runs without words: the schedule
is written, the meter is built, and the recap is `recap_sentence`, the plain one the close already
falls back to when the tutor cannot speak. The learner still gets everything that *matters*
out of an ending: what they demonstrated, and when to come back.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
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
    SessionStatus,
    StubGrader,
    StubTutor,
)

_BUDGET_S = 1800.0


class CountingTutor(StubTutor):
    """The stub tutor, counting every time anything asks it to speak."""

    def __init__(self) -> None:
        super().__init__()
        self.spoke = 0

    async def teach(self, *args: object, **kwargs: object) -> str:
        self.spoke += 1
        return await super().teach(*args, **kwargs)  # type: ignore[arg-type]

    async def recap(self, *args: object, **kwargs: object) -> str:
        self.spoke += 1
        return await super().recap(*args, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def sessions() -> MemorySessionStore:
    return MemorySessionStore()


@pytest.fixture
def tutor() -> CountingTutor:
    return CountingTutor()


@pytest.fixture
async def client(
    tmp_path: Path, sessions: MemorySessionStore, tutor: CountingTutor
) -> AsyncIterator[httpx.AsyncClient]:
    settings = settings_for(tmp_path)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    service = LiveSessionService(
        resolve_graph_store(settings),
        sessions,
        knowledge=MemoryKnowledgeStore(),
        tutor=tutor,
        grader=StubGrader(),
        session_budget_s=_BUDGET_S,
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _opened(client: httpx.AsyncClient, topic: str = "How neural networks learn") -> dict:
    graph = (await client.post("/api/live/graphs", json={"topic": topic})).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


def _age(sessions: MemorySessionStore, session_id: str, *, by_s: float) -> None:
    """Move a session's start backwards, which is how its clock is read (never a sleep).

    The elapsed time is measured from the row's ``started_at`` precisely so a reload cannot reset
    it, so backdating the row is the only honest way to reach the far side of the budget.
    """
    row = sessions.load(session_id)
    sessions.save(row.model_copy(update={"started_at": row.started_at - timedelta(seconds=by_s)}))


# ── a look closes what the clock already ended ───────────────────────────────────────────────────


async def test_reading_an_expired_session_closes_it(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """The defect, stated plainly: before this, the row said `active` for ever."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S + 1)

    # Act
    read = await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    assert read.status_code == 200
    assert read.json()["status"] == "closed"
    # And written, not merely reported: a status that came back closed and was stored active would
    # be the same lie told one layer further out.
    assert sessions.load(opened["sessionId"]).status is SessionStatus.CLOSED


async def test_listing_closes_the_sessions_whose_time_is_up(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """The list is the screen a learner meets these on, so it is the one that has to be truthful.
    A row reading "In progress" three days after the session ended is the product lying about
    itself in the one place it summarises itself."""
    # Arrange
    expired = await _opened(client, "How neural networks learn")
    fresh = await _opened(client, "How vaccines train the immune system")
    _age(sessions, expired["sessionId"], by_s=_BUDGET_S + 1)

    # Act
    listed = (await client.get("/api/live/sessions")).json()

    # Assert
    by_id = {entry["sessionId"]: entry for entry in listed}
    assert by_id[expired["sessionId"]]["status"] == "closed"
    assert by_id[fresh["sessionId"]]["status"] == "active"


async def test_a_session_inside_its_budget_is_left_alone(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """The other half, and the one a careless implementation breaks: a learner who steps away for
    five minutes must not come back to a session that ended without them."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S / 2)

    # Act
    read = await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    assert read.json()["status"] == "active"


# ── the close a look performs is free ────────────────────────────────────────────────────────────


async def test_closing_on_a_look_asks_no_tutor(
    client: httpx.AsyncClient, sessions: MemorySessionStore, tutor: CountingTutor
) -> None:
    """A page load that spends money is a surprising thing for a page load to do, and this one would
    spend it on words nobody asked for. The ceremony still runs; only the prose is the plain one."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S + 1)
    before = tutor.spoke

    # Act
    await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Assert
    assert tutor.spoke == before


async def test_the_learner_still_gets_the_meter_and_the_recap(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """Free is not the same as empty. What matters out of an ending is what you demonstrated and
    when to come back, and both are computed from the record rather than written by a model."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S + 1)

    # Act
    ended = (await client.get(f"/api/live/sessions/{opened['sessionId']}")).json()

    # Assert
    closing = ended["turns"][-1]
    assert closing["move"]["kind"] == "close"
    assert closing["surface"]["kind"] == "mastery_meter"
    assert closing["tutor"].strip()


async def test_the_close_says_the_time_ran_out(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """Three ways a session can end now, and a trace that reads the same for all of them has lost
    the only thing that distinguishes them: the clock ran out, the learner asked, or the director
    had nothing left to teach."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S + 1)

    # Act
    ended = (await client.get(f"/api/live/sessions/{opened['sessionId']}")).json()

    # Assert
    reason = ended["turns"][-1]["move"]["reason"].lower()
    assert "ran out" in reason
    # And is not the wording of the ending a learner chose, which is the one it would otherwise be
    # confused with: both are closes that no director decided on the material.
    assert "you asked" not in reason


# ── expiring a session that never got a map ──────────────────────────────────────────────────────


async def test_an_expired_session_that_never_started_teaching_is_abandoned(
    client: httpx.AsyncClient, sessions: MemorySessionStore, tmp_path: Path
) -> None:
    """A session whose compile never landed has no map, nothing taught, and no meter worth showing.
    It is abandoned for the same reason ending one is (T3): a ceremony about nothing is worse than
    no ceremony."""
    # Arrange
    from lunaris_live.session import DirectorMove, MoveKind, Session, SessionTurn

    sessions.save(
        Session(
            session_id="s-stuck",
            graph_id="g-never-landed",
            topic="How vaccines work",
            status=SessionStatus.WARMING,
            started_at=datetime.now(UTC) - timedelta(seconds=_BUDGET_S + 1),
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

    # Act
    read = await client.get("/api/live/sessions/s-stuck")

    # Assert
    assert read.json()["status"] == "abandoned"


# ── a closed session stays closed ────────────────────────────────────────────────────────────────


async def test_looking_twice_does_not_close_twice(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """The ceremony is a turn. Run on every read, an expired session would grow a goodbye per page
    load, and a learner's transcript would fill with endings."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S + 1)
    first = (await client.get(f"/api/live/sessions/{opened['sessionId']}")).json()

    # Act
    second = (await client.get(f"/api/live/sessions/{opened['sessionId']}")).json()

    # Assert
    assert len(second["turns"]) == len(first["turns"])


async def test_an_expired_session_cannot_be_answered(
    client: httpx.AsyncClient, sessions: MemorySessionStore
) -> None:
    """The bound has to bind. Answering a session whose time is up must not take a turn, whether or
    not anything has looked at it yet."""
    # Arrange
    opened = await _opened(client)
    _age(sessions, opened["sessionId"], by_s=_BUDGET_S + 1)
    await client.get(f"/api/live/sessions/{opened['sessionId']}")

    # Act
    response = await client.post(
        f"/api/live/sessions/{opened['sessionId']}/turns",
        json={"answer": "Still here.", "answeringSeq": opened["turns"][-1]["seq"]},
    )

    # Assert
    assert response.status_code == 409


# ── a look must not tidy up underneath a turn ────────────────────────────────────────────────────


async def test_a_look_does_not_close_a_session_a_turn_is_still_inside(tmp_path: Path) -> None:
    """A rendezvous, never a sleep.

    The window is real: a learner answers at 29:59, the turn takes ten seconds inside the tutor, and
    another tab reads the session at 30:05. The lazy close writes unconditionally, so it either
    lands under the turn and makes the turn lose its own compare-and-set, or lands after it and
    overwrites a graded answer that was already paid for. Busy also means somebody *is* in this
    session, so it is not abandoned at all: the read gets the session as it stands and the next look
    closes it.
    """
    import asyncio

    class HeldTutor(StubTutor):
        def __init__(self) -> None:
            super().__init__()
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def teach(self, *args: object, **kwargs: object) -> str:
            self.entered.set()
            await asyncio.wait_for(self.release.wait(), 5)
            return await super().teach(*args, **kwargs)  # type: ignore[arg-type]

    settings = settings_for(tmp_path)
    store = MemorySessionStore()
    tutor = HeldTutor()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    service = LiveSessionService(
        resolve_graph_store(settings),
        store,
        knowledge=MemoryKnowledgeStore(),
        tutor=tutor,
        grader=StubGrader(),
        session_budget_s=_BUDGET_S,
        throttle=LiveSessionThrottle(open_daily_cap=0),
    )
    app.dependency_overrides[get_live_session_service] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Arrange: a session on the far side of its budget, with a turn held open inside the tutor.
        # Both flags reset AFTER the open, because opening a session teaches a turn too.
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
        _age(store, opened["sessionId"], by_s=_BUDGET_S + 1)

        # Act: look at it, from another tab, while that turn is still inside the tutor.
        read = await client.get(f"/api/live/sessions/{opened['sessionId']}")

        # Assert: the look left it alone, and the turn it was inside still lands.
        assert read.json()["status"] == "active"
        tutor.release.set()
        assert (await answering).status_code == 200
