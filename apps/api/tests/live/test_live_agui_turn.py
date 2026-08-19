"""Lunaris Live, Phase 2b T2 — the AG-UI stream driving a real turn.

T1 settled the frame sequence against a turn that had already happened: the stream replayed what
the store already said. That proved the path and nothing about the loop. This is the task where a
learner's answer arrives over AG-UI, the grader scores it, the belief moves, the director decides,
and the tutor's next words go out **as they are written** rather than when the turn is over.

Three claims, and they are separable:

1. **The run drives the loop.** A run carrying the learner's message advances the stored session —
   the same advance ``POST /{id}/turns`` makes, because it is the same loop (U2: the AG-UI stream is
   additive, it is not a second implementation).
2. **The tutor's words arrive in parts.** Pinned here as shape; the *timing* claim is pinned in
   ``packages/live/tests/test_turn_streaming.py`` with a tutor that deadlocks a buffering
   implementation. It cannot be pinned here: ``httpx.ASGITransport`` drains a streaming response to
   completion before the client reads a byte of it, so every frame "arrives" at once no matter what
   the server did (the same limit T1 hit when it tried to express a client disconnect).
3. **The run carries state.** A ``STATE_SNAPSHOT`` before ``RUN_FINISHED`` says where the session
   now is — which turn is in front of the learner, what it asks, how the last answer was judged,
   and whether the session is still open. Text is what the learner reads; state is what a surface
   renders around it, and T3's Tier 1 components are written against this frame.

Exercised through the real ASGI app: the router, the service, the loop and the store are the
production ones, with the stub tutor and grader standing in for the model.
"""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from lunaris_api.app import create_app
from lunaris_api.config import Settings, get_settings
from lunaris_live.session import StubTutor, TutorUnavailableError


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
    """A live session to answer in — P2a's REST surface, used as given (U2)."""
    graph = (
        await client.post("/api/live/graphs", json={"topic": "How neural networks learn"})
    ).json()
    return (await client.post("/api/live/sessions", json={"graphId": graph["graphId"]})).json()


def _run_input(*, answer: str | None, thread_id: str = "t", run_id: str = "r") -> dict[str, Any]:
    """The body an AG-UI client POSTs. ``answer`` is the learner's message, or ``None`` for the
    run a freshly-opened tab makes, which has nothing to say yet."""
    messages = [{"id": "m1", "role": "user", "content": answer}] if answer is not None else []
    return {
        "threadId": thread_id,
        "runId": run_id,
        "state": {},
        "messages": messages,
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }


async def _events(
    client: httpx.AsyncClient, session_id: str, *, answer: str | None = None, run_id: str = "r"
) -> list[dict[str, Any]]:
    """Every AG-UI event of one run, decoded. Fails loudly on a non-200, since a status is a
    different contract from a stream and a test that silently accepted either proves neither."""
    collected: list[dict[str, Any]] = []
    async with client.stream(
        "POST",
        f"/api/live/sessions/{session_id}/agui",
        json=_run_input(answer=answer, run_id=run_id),
    ) as response:
        assert response.status_code == 200, await response.aread()
        async for line in response.aiter_lines():
            if line.startswith("data:"):
                collected.append(json.loads(line.removeprefix("data:").strip()))
    return collected


def _of_type(events: list[dict[str, Any]], type_: str) -> list[dict[str, Any]]:
    return [event for event in events if event["type"] == type_]


def _streamed(events: list[dict[str, Any]]) -> str:
    return "".join(event["delta"] for event in _of_type(events, "TEXT_MESSAGE_CONTENT"))


# ── the run drives the loop ────────────────────────────────────────────────────────────────────


async def test_a_run_carrying_an_answer_takes_the_next_turn(client: httpx.AsyncClient) -> None:
    """The task's first claim: this is the loop, not a replay of it.

    Pinned on the *stored* session rather than on the frames — a stream can say anything, and what
    makes this a turn is that the session a reloaded tab re-reads has moved on.
    """
    # Arrange
    session = await _session(client)
    asked = session["turns"][-1]

    # Act
    await _events(client, session["sessionId"], answer="A gradient points downhill.")

    # Assert — the answered turn now carries the learner's words and a verdict, and a new turn
    # stands in front of them.
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert len(reread["turns"]) == len(session["turns"]) + 1
    answered = reread["turns"][asked["seq"] - 1]
    assert answered["answer"] == "A gradient points downhill."
    assert answered["grade"] is not None


async def test_the_words_streamed_are_the_words_the_turn_stored(
    client: httpx.AsyncClient,
) -> None:
    """A surface fed by the stream and a session re-read after a reload must not disagree about
    what the tutor said — the second would rewrite the lesson the learner just had."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="Downhill, I think.")

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert _streamed(events) == reread["turns"][-1]["tutor"]


async def test_the_tutors_words_arrive_in_more_than_one_frame(client: httpx.AsyncClient) -> None:
    """The task's RED assertion, in the shape this layer can actually hold.

    Whether the fragments left the server *while the turn was still running* is pinned one layer
    down, where a tutor can be made to block until its first fragment has been relayed. What this
    proves is that the transport carries a lesson as fragments at all — a server that concatenated
    them into one frame would render identically and stream nothing.
    """
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="Something worth grading.")

    # Assert
    content = _of_type(events, "TEXT_MESSAGE_CONTENT")
    assert len(content) > 1, f"a lesson delivered in one frame is not a stream; saw {len(content)}"


async def test_a_run_with_nothing_to_say_replays_rather_than_taking_a_turn(
    client: httpx.AsyncClient,
) -> None:
    """A reloaded tab opens a run before the learner has typed anything, and it must get the turn
    they are looking at rather than an empty answer graded as a miss.

    An empty answer would be scored: ``StubGrader`` and every real grader would read silence as a
    failure to meet the criterion, so the belief would move on evidence the learner never gave.
    """
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer=None)

    # Assert — the turn in front of them, and the session unchanged behind it.
    assert _streamed(events) == session["turns"][-1]["tutor"]
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["turns"] == session["turns"]


async def test_a_blank_message_is_not_an_answer(client: httpx.AsyncClient) -> None:
    """An empty composer submitted by accident, or a client that pads its messages.

    Whitespace is silence, and silence graded is a belief moved on evidence nobody gave — the exact
    corruption U1's separate grader exists to keep out of the learner model. So it takes the replay
    path, like a run that carried no message at all.
    """
    # Arrange
    session = await _session(client)

    # Act
    await _events(client, session["sessionId"], answer="   \n  ")

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["turns"] == session["turns"]


async def test_only_the_learners_latest_message_is_taken_as_the_answer(
    client: httpx.AsyncClient,
) -> None:
    """CopilotKit sends the whole thread on every run, so by the third turn the body carries three
    answers. Taking the earliest would re-grade a session's history against the question currently
    in front of the learner, on every single turn.
    """
    # Arrange
    session = await _session(client)
    asked = session["turns"][-1]

    # Act — a thread, not a single message: the shape a real client sends after a turn or two.
    async with client.stream(
        "POST",
        f"/api/live/sessions/{session['sessionId']}/agui",
        json={
            "threadId": "t",
            "runId": "r",
            "state": {},
            "messages": [
                {"id": "m1", "role": "user", "content": "An answer from three turns ago."},
                {"id": "m2", "role": "assistant", "content": "The tutor's reply."},
                {"id": "m3", "role": "user", "content": "What I am saying now."},
            ],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        },
    ) as response:
        assert response.status_code == 200, await response.aread()
        await response.aread()

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["turns"][asked["seq"] - 1]["answer"] == "What I am saying now."


async def test_the_turn_is_logged_under_the_run_id_the_client_sent(
    client: httpx.AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """R5, on the path that actually spends money.

    The transport's own correlation is pinned in ``test_live_agui_stream.py``, but that run only
    reads a row. This one runs the director, a grader and a tutor — so if the id is re-minted here,
    the layer with every cost event and every model call in it is the one layer that cannot be
    tied back to the browser that started it. Read off the stdout JSON rather than structlog's
    ``capture_logs``, which cannot intercept a module logger another test has already cached.
    """
    # Arrange
    session = await _session(client)
    capsys.readouterr()  # discard the opening's own lines

    # Act
    await _events(client, session["sessionId"], answer="Downhill.", run_id="run-of-the-turn")

    # Assert — the turn's own line, under the browser's id, and the stored turn agrees.
    events = {
        line.get("event")
        for line in _json_log_lines(capsys)
        if line.get("run_id") == "run-of-the-turn"
    }
    assert "live.session.answered" in events, f"the turn left no trace; saw {events}"
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["turns"][-1]["runId"] == "run-of-the-turn", (
        "the transcript has to name the run that produced it, or a stored turn is unattached "
        "to the logs that explain it"
    )


def _json_log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """The structured stdout log lines emitted so far (the project logs JSON to stdout)."""
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("{") and line.endswith("}")
    ]


# ── the run carries state ──────────────────────────────────────────────────────────────────────


async def test_every_run_ends_with_the_state_the_session_is_now_in(
    client: httpx.AsyncClient,
) -> None:
    """The frame T3's components are written against.

    Ordered before ``RUN_FINISHED`` deliberately: a client that treats the run's end as "settled"
    would render the previous turn's state for the length of the next one if the snapshot came
    after it.
    """
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="An answer worth a verdict.")

    # Assert
    assert [event["type"] for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        *["TEXT_MESSAGE_CONTENT"] * len(_of_type(events, "TEXT_MESSAGE_CONTENT")),
        "TEXT_MESSAGE_END",
        # T3's Tier 1 card, then T5's Tier 2 layout. Pinned here as well as in the surfaces and
        # layout suites, because this is the test that owns the *sequence* — a card emitted in the
        # wrong place is a card answered against the wrong question, and a layout emitted before
        # the card it slots would paint a hole.
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
        "STATE_SNAPSHOT",
        "RUN_FINISHED",
    ]


async def test_the_state_says_what_the_learner_is_now_being_asked(
    client: httpx.AsyncClient,
) -> None:
    """State is not a copy of the text. The surface needs the turn's number to key a component to
    it, the staged do-statement to render an answer control for it, and the status to know whether
    to offer one at all."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer="A serious attempt.")

    # Assert
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    standing = reread["turns"][-1]
    snapshot = _of_type(events, "STATE_SNAPSHOT")[-1]["snapshot"]
    assert snapshot["sessionId"] == session["sessionId"]
    assert snapshot["status"] == reread["status"]
    assert snapshot["turn"] == standing["seq"]
    assert snapshot["criterion"] == standing["criterion"]["statement"]


async def test_the_state_carries_the_verdict_on_the_answer_just_given(
    client: httpx.AsyncClient,
) -> None:
    """The learner is owed the judgement, and a surface cannot show it from the tutor's prose: the
    grade is a separate agent's structured verdict (U1), which is the whole reason the mastery
    evidence is trustworthy. Without it on the wire, a component could only guess."""
    # Arrange
    session = await _session(client)
    asked = session["turns"][-1]

    # Act
    events = await _events(client, session["sessionId"], answer="It goes downhill.")

    # Assert — the same verdict the store recorded, not a second opinion.
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    recorded = reread["turns"][asked["seq"] - 1]["grade"]
    snapshot = _of_type(events, "STATE_SNAPSHOT")[-1]["snapshot"]
    assert snapshot["grade"] == recorded


async def test_a_replay_carries_state_too_and_no_verdict(client: httpx.AsyncClient) -> None:
    """One contract for both kinds of run. A surface that only received state when an answer was
    sent would have nothing to render on the reload U2 exists to make work — and the grade is
    ``None`` because nothing was judged, which is not the same as "judged and failed"."""
    # Arrange
    session = await _session(client)

    # Act
    events = await _events(client, session["sessionId"], answer=None)

    # Assert
    snapshot = _of_type(events, "STATE_SNAPSHOT")[-1]["snapshot"]
    assert snapshot["turn"] == session["turns"][-1]["seq"]
    assert snapshot["grade"] is None


# ── the failures a learner can act on ──────────────────────────────────────────────────────────


async def test_answering_a_closed_session_is_a_status_not_a_frame(
    client: httpx.AsyncClient,
) -> None:
    """Refusals that exist *before* the response begins stay statuses — Phase 1 settled that shape
    and P2a's REST surface answers 409 for exactly this. A learner with a stale tab must be told the
    session ended, in the same words, whichever transport they are on.
    """
    # Arrange — answer every question with the tutor's own words, which is what the offline grader
    # scores as met, until the director runs out of map and closes. Driven over AG-UI throughout,
    # so this also stands as the proof that a whole session can be taken on this transport alone.
    session = await _session(client)
    session_id = session["sessionId"]
    for _ in range(12):
        if session["status"] != "active":
            break
        await _events(client, session_id, answer=session["turns"][-1]["tutor"])
        session = (await client.get(f"/api/live/sessions/{session_id}")).json()
    assert session["status"] == "closed", "the director never ran out of material"

    # Act
    response = await client.post(
        f"/api/live/sessions/{session_id}/agui", json=_run_input(answer="One more?")
    )

    # Assert
    assert response.status_code == 409, response.text
    assert response.headers.get("x-session-id") == session_id


async def test_a_tutor_that_dies_mid_turn_closes_its_message_before_it_says_so(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The live turn's real failure path — and the one T1 could not have.

    T1's stream read a stored row, so nothing could break after the response began. A live turn can:
    the tutor's provider goes down halfway through writing. By then the status is spent, so the
    failure can only be a ``RUN_ERROR`` frame — but the message opened at the top of the run must be
    **closed first**. A client holding an open message treats it as a tutor still typing, so it
    waits through the very frame that was sent to stop it waiting.
    """
    # Arrange — the turn fails inside the loop, after the run has begun.
    session = await _session(client)

    async def _collapse(*_args: object, **_kwargs: object) -> AsyncIterator[str]:
        # An async *generator* that raises, not a coroutine that does: the loop iterates this with
        # ``async for``, so a plain coroutine would fail with a TypeError and the test would pass
        # while never exercising a tutor failure at all.
        yield "The first half of a sentence"
        raise TutorUnavailableError("the provider went away mid-sentence")

    monkeypatch.setattr(StubTutor, "stream", _collapse)

    # Act
    events = await _events(client, session["sessionId"], answer="An answer worth teaching after.")

    # Assert — the message is shut before the failure is announced, and no state is claimed.
    assert [event["type"] for event in events] == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "RUN_ERROR",
    ]
    assert events[-1]["code"] == "run_failed"
    # And nothing was persisted: a half-written lesson is not a turn, so the learner's retry means
    # exactly what they expect it to.
    reread = (await client.get(f"/api/live/sessions/{session['sessionId']}")).json()
    assert reread["turns"] == session["turns"]
