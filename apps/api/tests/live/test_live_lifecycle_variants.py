"""Every lifecycle verb against every state a session can be in (T10).

The journey's closing task, and the one that stops the previous nine from being a set of special
cases that happen to work. Each verb was built against the state it was designed for; this is the
cross product, so a state nobody thought about while writing a verb still has a defined answer.

The table is keyed off ``SessionStatus`` itself and asserted to cover it (``table == enum``, the
idiom P2b settled). Adding a sixth status fails this file rather than quietly inheriting whatever
the last ``elif`` happened to do — which is exactly how T3's ``abandoned`` reached the API without
the web ever learning about it (T9).
"""

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

#: What each verb leaves behind, per status. `None` means the session is gone.
#:
#: Read as a specification rather than as a record of what the code does: a cell that surprises a
#: reader is a cell worth arguing about, which is the point of writing it out flat.
_AFTER_END = {
    # Nothing has been taught yet, so there is no ceremony to hold: leaving is the honest ending.
    SessionStatus.PLACING: SessionStatus.ABANDONED,
    SessionStatus.WARMING: SessionStatus.ABANDONED,
    # The one that gets the recap, the mastery delta and the review day.
    SessionStatus.ACTIVE: SessionStatus.CLOSED,
    # Terminal already: idempotent, and no second goodbye is paid for.
    SessionStatus.CLOSED: SessionStatus.CLOSED,
    SessionStatus.ABANDONED: SessionStatus.ABANDONED,
}

_AFTER_DISCARD = {
    SessionStatus.PLACING: SessionStatus.ABANDONED,
    SessionStatus.WARMING: SessionStatus.ABANDONED,
    SessionStatus.ACTIVE: SessionStatus.ABANDONED,
    # Leaving something that already ended well must not rewrite how it ended.
    SessionStatus.CLOSED: SessionStatus.CLOSED,
    SessionStatus.ABANDONED: SessionStatus.ABANDONED,
}

#: Whether a topic can be forgotten while a session sits in this state. A live session writes its
#: model back at the end of every turn, so a reset underneath one would be silently undone (AD18).
_FORGETTABLE = {
    SessionStatus.PLACING: False,
    SessionStatus.WARMING: False,
    SessionStatus.ACTIVE: False,
    SessionStatus.CLOSED: True,
    SessionStatus.ABANDONED: True,
}


def test_the_table_covers_every_status() -> None:
    """The guard that makes the rest of this file mean something. A status missing from a table is
    a verb with undefined behaviour, and it would be found by a learner rather than here."""
    for table in (_AFTER_END, _AFTER_DISCARD, _FORGETTABLE):
        assert set(table) == set(SessionStatus)


@pytest.fixture
def sessions() -> MemorySessionStore:
    return MemorySessionStore()


@pytest.fixture
async def client(tmp_path: Path, sessions: MemorySessionStore) -> AsyncIterator[httpx.AsyncClient]:
    settings = settings_for(tmp_path)
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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _seeded(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> dict:
    """A session in ``status``, on a real compiled map where the status needs one.

    ACTIVE and the terminal pair are opened through the API so they carry a real map and a real
    first turn — a close needs both. PLACING and WARMING are written straight to the store, because
    reaching them through the API means standing up a compile plane, an interviewer and a prior
    mapper to observe a status, and what is under test here is the verb.
    """
    if status in (SessionStatus.PLACING, SessionStatus.WARMING):
        seeded = Session(
            session_id=f"s-{status.value}",
            graph_id="g-pending",
            topic="How vaccines work",
            status=status,
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
        sessions.save(seeded)
        return {"sessionId": seeded.session_id, "graphId": seeded.graph_id}

    graph = (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()
    opened = (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()
    if status is SessionStatus.CLOSED:
        await client.post(f"/api/live/sessions/{opened['sessionId']}/end")
    elif status is SessionStatus.ABANDONED:
        await client.post(f"/api/live/sessions/{opened['sessionId']}/discard")
    return opened


# ── ending ───────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", list(SessionStatus))
async def test_ending_a_session_in_any_state(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> None:
    # Arrange
    seeded = await _seeded(client, sessions, status)

    # Act
    response = await client.post(f"/api/live/sessions/{seeded['sessionId']}/end")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == _AFTER_END[status].value


# ── leaving ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", list(SessionStatus))
async def test_leaving_a_session_in_any_state(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> None:
    # Arrange
    seeded = await _seeded(client, sessions, status)

    # Act
    response = await client.post(f"/api/live/sessions/{seeded['sessionId']}/discard")

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == _AFTER_DISCARD[status].value


# ── deleting ─────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", list(SessionStatus))
async def test_deleting_a_session_in_any_state(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> None:
    """Always allowed, whatever state it is in. A learner asking for their words to be removed is
    not asking a question about the session's lifecycle."""
    # Arrange
    seeded = await _seeded(client, sessions, status)

    # Act
    response = await client.delete(f"/api/live/sessions/{seeded['sessionId']}")

    # Assert
    assert response.status_code == 204
    assert (await client.get(f"/api/live/sessions/{seeded['sessionId']}")).status_code == 404


# ── forgetting ───────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", list(SessionStatus))
async def test_forgetting_a_topic_with_a_session_in_any_state(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> None:
    # Arrange
    seeded = await _seeded(client, sessions, status)

    # Act
    response = await client.delete(f"/api/live/knowledge/{seeded['graphId']}")

    # Assert
    assert response.status_code == (204 if _FORGETTABLE[status] else 409)


@pytest.mark.parametrize("status", list(SessionStatus))
async def test_a_refused_reset_says_what_to_do_about_it(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> None:
    """A refusal that only says no is a dead end, and this one has an exit: finish or leave the
    session first. Asserted across the table because the instruction has to be true of every state
    that produces it."""
    if _FORGETTABLE[status]:
        pytest.skip("nothing refuses this one")
    # Arrange
    seeded = await _seeded(client, sessions, status)

    # Act
    response = await client.delete(f"/api/live/knowledge/{seeded['graphId']}")

    # Assert
    detail = response.json()["detail"].lower()
    assert "finish" in detail or "leave" in detail


# ── the list agrees with the verb that was just used ─────────────────────────────────────────────


@pytest.mark.parametrize("status", list(SessionStatus))
async def test_the_listing_reports_what_the_verb_left_behind(
    client: httpx.AsyncClient, sessions: MemorySessionStore, status: SessionStatus
) -> None:
    """The screen the verbs are pressed on has to agree with what they did. A row still reading
    "in progress" after a learner left it is the surface disagreeing with the row behind it."""
    # Arrange
    seeded = await _seeded(client, sessions, status)
    await client.post(f"/api/live/sessions/{seeded['sessionId']}/discard")

    # Act
    listed = (await client.get("/api/live/sessions")).json()

    # Assert
    row = next(entry for entry in listed if entry["sessionId"] == seeded["sessionId"])
    assert row["status"] == _AFTER_DISCARD[status].value
