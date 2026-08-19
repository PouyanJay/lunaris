"""Lunaris Live, Phase 2b — the session as an AG-UI stream.

P2a's surface was a transcript: the learner posted an answer and got the whole session back. That
contract stays (U2's resume depends on it), but it can only ever hand over a finished turn. This is
the transport the generative surfaces need — the one that can say "the tutor is partway through a
sentence", "mount this component", "the estimate for that concept just moved".

The wire is **AG-UI**, spoken by `ag-ui-protocol` on this side and consumed by CopilotKit on the
other, with a Node runtime in between. T1 is the walking skeleton: every layer of that path carries
one run, and the words that come out are the ones really in the store rather than a fixture the
endpoint invented. What this file holds is the part of the contract that is about the *transport* —
frame order, id echoing, correlation, and which failures are statuses. The turn it carries is T2's,
and lives in `test_live_agui_turn.py`.

Exercised through the real ASGI app over httpx; the stub compiler and tutor stand in for the model,
while the router, the service and the store are the production ones.
"""

import json
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_api.live.session.agui.replayed_turn import replayed_turn
from lunaris_api.live.session.agui.turn_events import turn_events
from lunaris_api.live.session.turn_beat import TurnBeat
from lunaris_live.session import Session, SessionStatus


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        pipeline="stub", course_dir=tmp_path, cors_origins=(), env_file=tmp_path / ".env"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


async def _session(client: httpx.AsyncClient) -> dict:
    """A live session to stream over — P2a's surface, used as given."""
    graph = (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


def _run_input(*, thread_id: str, run_id: str) -> dict[str, Any]:
    """The body an AG-UI client POSTs, in full.

    ``state`` and ``forwardedProps`` are required by the protocol and always sent by the real
    client, so a test that omitted them would be exercising a shape nothing produces — and would
    pass against an endpoint that rejects every genuine request.
    """
    return {
        "threadId": thread_id,
        "runId": run_id,
        "state": {},
        "messages": [],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


async def _events(
    client: httpx.AsyncClient, session_id: str, *, thread_id: str, run_id: str
) -> tuple[list[dict[str, Any]], httpx.Headers]:
    """Every AG-UI event of one run, decoded, plus the response headers.

    AG-UI frames carry no ``event:`` line — the type is a field inside the payload — so this reads
    ``data:`` lines only. That is the encoder's format, not a simplification of it.
    """
    collected: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/live/sessions/{session_id}/agui",
        json=_run_input(thread_id=thread_id, run_id=run_id),
    ) as response:
        assert response.status_code == 200, await response.aread()
        headers = response.headers
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                collected.append(json.loads(line.removeprefix("data:").strip()))
    return collected, headers


async def test_a_run_streams_the_ag_ui_lifecycle_in_order(client: httpx.AsyncClient) -> None:
    """The frames CopilotKit's client is written against, in the order it expects them.

    Order is the contract, not decoration: a ``TEXT_MESSAGE_CONTENT`` arriving before its
    ``TEXT_MESSAGE_START`` has no message to attach to, and the client drops it. Pinned as a
    sequence rather than a set for exactly that reason.
    """
    # Arrange
    session = await _session(client)

    # Act
    events, headers = await _events(
        client, session["sessionId"], thread_id="thread-1", run_id="run-1"
    )

    # Assert
    assert headers["content-type"].startswith("text/event-stream")
    assert [event["type"] for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        # T3's Tier 1 card, then T5's Tier 2 layout around it — both between the words they
        # follow and the state that settles the run. The layout comes second because it holds a
        # slot for the card.
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "STATE_SNAPSHOT",
        "RUN_FINISHED",
    ]


async def test_the_run_carries_back_the_ids_the_client_sent(client: httpx.AsyncClient) -> None:
    """AG-UI correlates a stream to the run that asked for it by these two ids.

    The client holds several runs at once on one thread; echoing a *different* id — or minting a
    fresh one server-side — leaves it unable to attach the frames to anything, which surfaces as a
    session that streams into a void.
    """
    # Arrange
    session = await _session(client)

    # Act
    events, _ = await _events(client, session["sessionId"], thread_id="thread-7", run_id="run-9")

    # Assert
    lifecycle = [e for e in events if e["type"] in {"RUN_STARTED", "RUN_FINISHED"}]
    assert lifecycle, "a run with no lifecycle frames cannot be correlated at all"
    assert all(event["threadId"] == "thread-7" for event in lifecycle)
    assert all(event["runId"] == "run-9" for event in lifecycle)


async def test_the_words_streamed_are_the_ones_in_the_store(client: httpx.AsyncClient) -> None:
    """The whole point of the skeleton: the stream reaches the session row, not a fixture.

    A hardcoded greeting would satisfy every assertion about shape and order above while proving
    nothing about the path — so this pins the content against what P2a's surface independently says
    is in the session.
    """
    # Arrange
    session = await _session(client)
    taught = session["turns"][-1]["tutor"]
    assert taught, "the fixture is only meaningful if the stored turn actually has words"

    # Act
    events, _ = await _events(client, session["sessionId"], thread_id="t", run_id="r")

    # Assert
    streamed = "".join(
        event["delta"] for event in events if event["type"] == "TEXT_MESSAGE_CONTENT"
    )
    assert streamed == taught


async def test_every_text_frame_belongs_to_the_message_that_opened(
    client: httpx.AsyncClient,
) -> None:
    """One ``message_id`` per message, or the client cannot assemble the deltas into a sentence."""
    # Arrange
    session = await _session(client)

    # Act
    events, _ = await _events(client, session["sessionId"], thread_id="t", run_id="r")

    # Assert
    text_frames = [event for event in events if event["type"].startswith("TEXT_MESSAGE_")]
    message_ids = {event["messageId"] for event in text_frames}
    assert len(message_ids) == 1, f"one message, one id; saw {message_ids}"
    opening = next(event for event in text_frames if event["type"] == "TEXT_MESSAGE_START")
    assert opening["role"] == "assistant", "the tutor speaks as the assistant, not as the learner"


async def test_the_run_is_logged_under_the_id_the_client_sent(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Correlation has to survive the crossing (R5).

    The run is minted in the browser and travels through a Node runtime before it reaches Python,
    so a server that logs under an id of its own making leaves three runtimes' logs with no shared
    key — and the first production incident on this path untriangulable. Read off the stdout JSON
    rather than structlog's ``capture_logs``, which cannot intercept a module logger another test
    has already cached (house pattern).
    """
    # Arrange
    session = await _session(client)
    capsys.readouterr()  # discard the opening's own lines, so only the stream's remain

    # Act
    await _events(client, session["sessionId"], thread_id="t", run_id="run-correlated")

    # Assert
    correlated = [
        line for line in _json_log_lines(capsys) if line.get("run_id") == "run-correlated"
    ]
    events = {line.get("event") for line in correlated}
    # This line passes no ids of its own, so it can only be correlated if the contextvars binding
    # propagated — which is what stops the test passing when the binding is deleted and the id is
    # merely threaded through arguments by hand.
    assert "live.agui.run_finished" in events, f"the run left no trace; saw {events}"
    assert all(line.get("session_id") == session["sessionId"] for line in correlated)


async def test_an_unknown_session_is_refused_before_the_stream_opens(
    client: httpx.AsyncClient,
) -> None:
    """A 404, not a stream carrying an error frame.

    Phase 1 settled this shape for the compile stream: a failure that exists *before* the response
    begins is a status, because the status has not left yet. Answering 200 and then explaining
    inside the body would make every client parse a success to discover a failure.
    """
    # Act
    response = await client.post(
        "/api/live/sessions/nope/agui",
        json=_run_input(thread_id="t", run_id="r"),
    )

    # Assert
    assert response.status_code == 404, response.text
    assert response.headers.get("x-session-id") == "nope", (
        "the id must ride the failure, or the learner reporting it cannot name it"
    )


async def test_a_session_with_no_turns_still_opens_and_closes_its_message() -> None:
    """The empty branch, exercised through the only state that can actually reach it.

    ``turn_events`` deliberately opens a message even when there is nothing in it: a client that
    has begun a run and never receives a message end has nothing to close, and waits.

    Reaching that branch takes a session with *no turns*, not a turn with no words — ``tutor`` is
    ``min_length=1``, so a wordless turn cannot be constructed at all. Worth knowing, because a test
    aimed at the wrong one of those two passes by never running the branch.
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

    # Assert — a message that opens and closes, carrying no content frame, and state regardless:
    # a surface with nothing to render still has to be told the session is open.
    assert [event.type.value for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_END",
        "STATE_SNAPSHOT",
        "RUN_FINISHED",
    ]


async def test_a_failure_after_the_stream_opens_arrives_as_a_frame(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The status is already spent by then, so the only way left to say so is a frame.

    Without it the client sees a stream that simply stops, which is indistinguishable from a tutor
    still thinking — so it waits instead of telling the learner anything. Phase 1 settled this shape
    for the compile stream; the same reasoning holds here.
    """
    # Arrange — break the translation itself, which runs after the response has begun.
    session = await _session(client)

    def _explode(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("the turn came apart mid-stream")

    # Addressed through ``sys.modules`` rather than by dotted path: ``agui/__init__.py`` re-exports
    # ``router``, which shadows the submodule of the same name, so the dotted form resolves to the
    # APIRouter object instead of the module.
    monkeypatch.setattr(
        sys.modules["lunaris_api.live.session.agui.router"], "turn_events", _explode
    )

    # Act
    events, headers = await _events(client, session["sessionId"], thread_id="t", run_id="r")

    # Assert — a 200 that then explains itself, not a silent truncation.
    assert headers["content-type"].startswith("text/event-stream")
    assert [event["type"] for event in events] == ["RUN_ERROR"]
    assert events[0]["code"] == "run_failed"


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


async def test_an_empty_fragment_never_reaches_the_wire() -> None:
    """``TextMessageContentEvent`` refuses an empty delta, and a run that produced one would die
    mid-stream — a validation error inside the body, surfacing to the learner as a turn that broke
    for no reason they can see.

    No producer emits one today (the streaming tutor drops its own blanks, and a stored turn's
    ``tutor`` is ``min_length=1``), which is exactly why this is pinned here rather than left to be
    discovered by whichever future producer is less careful.
    """

    # Arrange
    async def with_a_gap() -> AsyncIterator[tuple[str, str | Session]]:
        yield "delta", "Some words"
        yield "delta", ""
        yield "delta", " and more."
        yield (
            "session",
            Session(
                session_id="s1",
                graph_id="g1",
                status=SessionStatus.ACTIVE,
                started_at=datetime.now(UTC),
                turns=[],
            ),
        )

    # Act
    events = [event async for event in turn_events(with_a_gap(), thread_id="t", run_id="r")]

    # Assert — two content frames, and the lesson is still whole.
    content = [event for event in events if event.type.value == "TEXT_MESSAGE_CONTENT"]
    assert [frame.delta for frame in content] == ["Some words", " and more."]


async def test_a_beat_this_transport_does_not_know_is_loud_rather_than_dropped() -> None:
    """T3 through T5 each add a producer to this stream, and each is a chance to yield a name that
    does not exist.

    An earlier version leaned on ``isinstance`` for the terminal case, so a payload matching neither
    predicate simply vanished: no frame, no error, no log, and a state snapshot that quietly never
    arrived. A run rendering the wrong thing is a bug somebody notices; a run silently rendering
    nothing is one that gets diagnosed as "the model was slow".
    """

    # Arrange
    async def with_a_bogus_beat() -> AsyncIterator[tuple[TurnBeat, str | Session]]:
        yield "surface", "a beat from a future task"  # type: ignore[misc]

    # Act / Assert
    with pytest.raises(ValueError, match="surface"):
        async for _ in turn_events(with_a_bogus_beat(), thread_id="t", run_id="r"):
            pass
