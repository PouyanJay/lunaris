"""Tier 1 on the wire: the card the director chose, carried as a tool call (Phase 2b, T3).

CopilotKit renders a controlled component by *calling a tool the frontend registered* — which is
exactly the shape plan §8's Tier 1 asks for, with one difference that matters: the caller here is
not a model. The arguments are `select_surface`'s output, a pure function of the move, the map and
the belief, so what the learner is assessed by is auditable from the frame alone.

One tool, `lunaris.surface`, whose arguments are the discriminated `SurfaceSpec`. Five separate
tools would mean five registrations on the browser side, each free to drift from the Python enum
that decides which of them is ever called.

Exercised through the real ASGI app: the router, the service, the loop and the store are the
production ones, with the stub tutor and grader standing in for the model.
"""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from _agui_frames import call_named, tool_names
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.session.agui.replayed_turn import replayed_turn
from lunaris_api.live.session.agui.surface_tool import SURFACE_TOOL
from lunaris_api.live.session.agui.turn_events import turn_events
from lunaris_live.session import Session, SessionStatus, SessionTurn


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _session(client: httpx.AsyncClient) -> dict[str, Any]:
    graph = (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


async def _events(
    client: httpx.AsyncClient, session_id: str, *, answer: str | None = None
) -> list[dict[str, Any]]:
    messages = [{"id": "m1", "role": "user", "content": answer}] if answer is not None else []
    collected: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/live/sessions/{session_id}/agui",
        json={
            "threadId": "t",
            "runId": "r",
            "state": {},
            "messages": messages,
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                collected.append(json.loads(line.removeprefix("data:").strip()))
    return collected


def _surface_in(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The Tier 1 spec the run carried."""
    return call_named(events, SURFACE_TOOL)


def _surface_call_id_in(events: list[dict[str, Any]]) -> str:
    """The id the run's card went out under."""
    return next(
        event["toolCallId"]
        for event in events
        if event["type"] == "TOOL_CALL_START" and event["toolCallName"] == SURFACE_TOOL
    )


def _snapshot_in(events: list[dict[str, Any]]) -> dict[str, Any]:
    """The state frame the run ended on."""
    return next(event["snapshot"] for event in events if event["type"] == "STATE_SNAPSHOT")


async def test_a_turn_carries_the_card_the_director_chose(client: httpx.AsyncClient) -> None:
    """The task's claim on the wire: the component and its props ride the run.

    Asserted against the *stored* turn rather than against a shape, because what makes this Tier 1
    rather than decoration is that the frame and the session row are the same decision — a surface
    that streamed one card and recorded another would corrupt the audit trail while looking correct.
    """
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert _surface_in(events) == reread["turns"][-1]["surface"]


async def test_the_state_names_the_card_that_is_standing(client: httpx.AsyncClient) -> None:
    """P2b T10. CopilotKit keeps every card in the thread on screen, so a browser needs to know
    which one is the question in front of the learner and which are the record: the state frame
    carries the tool-call id of the standing card, and only a card whose id matches is answerable
    in place. A transport fact, so it lives on the transport's own projection rather than on the
    session (the session has no tool calls)."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    assert _snapshot_in(events)["surfaceCallId"] == _surface_call_id_in(events)


async def test_a_replay_names_the_card_it_replays(client: httpx.AsyncClient) -> None:
    """A reloaded tab gets the standing card again under a fresh id (T3), so the id it is told is
    standing has to be *that* one, not the one the live run minted."""
    session = await _session(client)
    await _events(client, session["sessionId"], answer="A serious attempt.")

    replay = await _events(client, session["sessionId"])

    assert _snapshot_in(replay)["surfaceCallId"] == _surface_call_id_in(replay)


async def test_the_card_is_named_by_the_tool_the_browser_registers(
    client: httpx.AsyncClient,
) -> None:
    """A contract between two separately deployed things: the name Python calls and the name the
    browser registers with `useCopilotAction`. Drift is a card that silently never renders — the run
    looks perfect from this side. Pinned as a literal here, and the web suite pins the same literal
    from its side, exactly as T1's mount path is."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    # The layout rides beside it from T5, and its own name is pinned in `test_live_agui_layout`.
    assert tool_names(events) == ["lunaris.surface", "lunaris.layout"]
    assert SURFACE_TOOL == "lunaris.surface"


async def test_the_card_arrives_after_the_words_and_before_the_state(
    client: httpx.AsyncClient,
) -> None:
    """Order is the contract. The card belongs *after* the explanation it follows — a quiz that
    appeared while the tutor was still setting it up would be answered against half a sentence — and
    *before* the state frame, so a client that treats the state as settled has already been handed
    everything the turn produced.
    """
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    order = [event["type"] for event in events]
    assert order.index("TEXT_MESSAGE_END") < order.index("TOOL_CALL_START")
    assert order.index("TOOL_CALL_END") < order.index("STATE_SNAPSHOT")
    assert order[-1] == "RUN_FINISHED"
    assert [event["toolCallId"] for event in events if "toolCallId" in event].count(
        next(e["toolCallId"] for e in events if e["type"] == "TOOL_CALL_START")
    ) == 3, "one call, three frames, one id — or the client cannot assemble the arguments"
    assert len({e["toolCallId"] for e in events if e["type"] == "TOOL_CALL_START"}) == 2, (
        "the card and its layout are separate calls, so they need separate ids"
    )


async def test_a_reloaded_tab_gets_the_card_it_was_halfway_through(
    client: httpx.AsyncClient,
) -> None:
    """The reason the spec is stored rather than re-derived (R4). A learner who reloads mid-answer
    must find the same question, not a fresh one chosen by rules that have since seen more evidence.
    """
    # Arrange — a session with a card standing in front of the learner.
    session = await _session(client)

    # Act — the run a freshly loaded tab makes, carrying no message.
    events = await _events(client, session["sessionId"], answer=None)

    # Assert
    assert _surface_in(events) == session["turns"][-1]["surface"]


async def test_a_turn_from_before_this_task_streams_without_a_card() -> None:
    """Every session P2a stored has no surface. The run must still be well-formed: a client waiting
    on tool frames that never come would sit on a spinner over a session that is perfectly readable.

    Driven against the translator rather than through the app, because that is where the branch is
    and planting a pre-T3 row in the app's store would mean reaching past the store's own contract
    to fake one. The with-surface case above proves the wiring; this proves the absence.
    """
    # Arrange — a turn exactly as P2a wrote one, parsed by today's schema.
    session = Session(
        session_id="s1",
        graph_id="g1",
        status=SessionStatus.ACTIVE,
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn.model_validate(
                {
                    "seq": 1,
                    "move": {"kind": "introduce", "nodeId": "gradient", "reason": "Because."},
                    "tutor": "Let's start with Gradient.",
                    "runId": "r1",
                }
            )
        ],
    )
    assert session.turns[0].surface is None, "the fixture is only meaningful without a surface"

    # Act
    events = [
        event async for event in turn_events(replayed_turn(session), thread_id="t", run_id="r")
    ]

    # Assert
    assert [event.type.value for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "STATE_SNAPSHOT",
        "RUN_FINISHED",
    ]


async def test_a_stuck_learner_gets_the_quiz_over_the_wire(client: httpx.AsyncClient) -> None:
    """The quiz path end to end, through the real director rather than a hand-built move.

    Every other test here drives an opening turn, whose move is always an INTRODUCE — so the tool
    call was only ever proven for one of the five cards. A quiz requires a learner the director has
    watched miss twice, which is the one surface whose props come from Phase 1's authored
    misconceptions rather than from the criterion in front of them.
    """
    # Arrange — two answers with nothing in them, which the offline grader scores as misses.
    session = await _session(client)
    session_id = session["sessionId"]
    await _events(client, session_id, answer="No idea, sorry.")

    # Act
    events = await _events(client, session_id, answer="Still no idea.")

    # Assert — the director remediated and the card followed it onto the wire.
    reread = (await client.get(f"/api/live/sessions/{session_id}")).json()
    standing = reread["turns"][-1]
    assert standing["move"]["kind"] == "remediate", (
        f"the director did not remediate; it chose {standing['move']['kind']}"
    )
    spec = _surface_in(events)
    assert spec["kind"] == "quiz_card"
    assert spec == standing["surface"]
    assert spec["nodeId"] == standing["move"]["nodeId"]
    assert len(spec["options"]) >= 2


async def test_a_session_with_no_turns_carries_no_card_either() -> None:
    """The other half of the "no card" branch, and the state only a stored row can be in.

    ``open_session`` always teaches before it returns, so a turn-less session cannot be created —
    but one can be read. The run has to stay well-formed around the silence: a message that opens
    and closes, state, and no tool frames to wait on.
    """
    # Arrange
    empty = Session(
        session_id="s1",
        graph_id="g1",
        status=SessionStatus.ACTIVE,
        started_at=datetime.now(UTC),
        turns=[],
    )

    # Act
    events = [event async for event in turn_events(replayed_turn(empty), thread_id="t", run_id="r")]

    # Assert
    assert [event.type.value for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_END",
        "STATE_SNAPSHOT",
        "RUN_FINISHED",
    ]
