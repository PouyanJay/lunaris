"""The tutor's words reaching the learner while they are still being written (Phase 2b, T2).

P2a's tutor answered in one piece: ``teach`` awaited a whole turn and the surface showed it once it
was finished. That is the right contract for the REST path and the wrong one for a live session — a
learner watching a cursor for twenty seconds cannot tell a tutor that is thinking from one that has
died, and P2b's whole premise is a surface that narrates itself.

So ``ITutor`` gains a streaming path (A2) and ``take_turn`` gains a sink to relay it through. Both
are additive: ``teach`` still exists, the REST endpoint still uses it, and a turn taken without a
sink is byte-for-byte P2a's turn.

The load-bearing claim here is about **timing**, and timing is the one thing a green test lies about
most easily — Phase 1's T7 shipped two tests that asserted "while still running" and awaited the
whole thing before looking. So ``GatedTutor`` below blocks until its first fragment has been
relayed: an implementation that buffers the turn and relays it at the end **deadlocks** rather than
passing.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence

import pytest
from langchain_core.messages import AIMessageChunk
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    TeachingSpec,
)
from lunaris_live.session import (
    ClaudeTutor,
    DirectorMove,
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    StubGrader,
    StubTutor,
    TutorUnavailableError,
    open_session,
    take_turn,
)

_BUDGET_S = 1800.0

#: Long enough that a deadlock is unambiguous, short enough that a deadlocked suite still ends.
_DEADLOCK_S = 2.0

#: The gate gives up first, deliberately. Both this and the test's own timeout fire on a deadlock,
#: and whichever wins decides which traceback a future reader gets — the tutor-side one says which
#: fragment never came, the outer one only says the test was slow.
_GATE_S = _DEADLOCK_S / 2


def _node(node_id: str = "a", name: str = "Alpha") -> ConceptNode:
    return ConceptNode(
        id=node_id,
        name=name,
        definition=f"What {name} is.",
        teaching_spec=TeachingSpec(objective=f"Use {name}.", misconceptions=[f"{name} is magic."]),
        mastery_criteria=[
            MasteryCriterion(
                kind=MasteryCriterionKind.EXPLAIN, statement=f"Explain {name} in your own words."
            )
        ],
    )


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[_node(), _node("b", "Beta")],
        topo_order=["a", "b"],
        is_acyclic=True,
    )


def _move() -> DirectorMove:
    return DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Because the test says so.")


async def _opened(tutor: object) -> Session:
    return (
        await open_session(
            _graph(),
            LearnerModel(graph_id="g1"),
            SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
            session_id="s1",
            run_id="r1",
            tutor=tutor,  # type: ignore[arg-type]
        )
    ).session


async def _answered(
    session: Session, tutor: object, *, on_delta: object | None = None, answer: str = "Alpha is X."
) -> Session:
    outcome = await take_turn(
        session,
        _graph(),
        LearnerModel(graph_id="g1"),
        answer=answer,
        answering_seq=session.turns[-1].seq,
        grader=StubGrader(),
        tutor=tutor,  # type: ignore[arg-type]
        run_id="r2",
        elapsed_s=1.0,
        budget_s=_BUDGET_S,
        on_delta=on_delta,  # type: ignore[arg-type]
    )
    return outcome.session


class StreamingModel:
    """A chat model that hands back one response in fragments, as a real one does."""

    def __init__(self, parts: Sequence[str]) -> None:
        self._parts = list(parts)
        self.prompts: list[str] = []

    async def astream(self, prompt: str) -> AsyncIterator[AIMessageChunk]:
        self.prompts.append(prompt)
        for part in self._parts:
            yield AIMessageChunk(content=part)


class GatedTutor:
    """Streams a first fragment, then refuses to write another word until that one has been relayed.

    This is what makes the timing claim real rather than asserted. A ``take_turn`` that collected
    every fragment before relaying any of them never sets the event, so this tutor waits forever and
    the test fails on the deadlock instead of passing on a technicality.
    """

    def __init__(self) -> None:
        self.first_was_relayed = asyncio.Event()

    async def teach(self, *_args: object, **_kwargs: object) -> str:
        raise AssertionError("a turn with a sink must stream rather than await the whole turn")

    async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[str]:
        yield "The first part. "
        async with asyncio.timeout(_GATE_S):
            await self.first_was_relayed.wait()
        yield "The rest of it."


# ── the tutor can speak in fragments ───────────────────────────────────────────────────────────


async def test_the_offline_tutor_streams_exactly_the_words_it_would_have_said_in_one_piece() -> (
    None
):
    """Two paths, one lesson. The stub is what CI and keyless dev are taught by, so a streaming path
    that drifted from the whole one would make every offline test of the loop a test of a different
    tutor than the surface actually shows."""
    # Arrange
    tutor = StubTutor()
    criterion = _node().mastery_criteria[0]

    # Act
    whole = await tutor.teach(_move(), _node(), topic="A subject", criterion=criterion, run_id="r")
    parts = [
        part
        async for part in tutor.stream(
            _move(), _node(), topic="A subject", criterion=criterion, run_id="r"
        )
    ]

    # Assert — and in more than one piece, or "streaming" is a word for the same behaviour.
    assert "".join(parts) == whole
    assert len(parts) > 1, "a stub that yields the whole turn at once cannot exercise a surface"


async def test_the_model_backed_tutor_passes_the_models_fragments_through_as_they_arrive() -> None:
    """The fragments the learner reads are the model's own, not a re-chunking of a finished answer:
    a tutor that awaited the whole response and then diced it would stream perfectly in a test and
    leave the learner waiting exactly as long as before."""
    # Arrange
    model = StreamingModel(["Picture the loss ", "as a hillside. ", "Which way is down?"])

    # Act
    parts = [
        part
        async for part in ClaudeTutor("m", client=model).stream(
            _move(), _node(), topic="A subject", run_id="r1"
        )
    ]

    # Assert
    assert parts == ["Picture the loss ", "as a hillside. ", "Which way is down?"]
    assert "What Alpha is." in model.prompts[0], "the streaming path teaches the same concept"


async def test_the_streaming_tutor_does_not_open_on_the_models_whitespace() -> None:
    """Models routinely clear their throat with a newline, and ``teach`` strips it.

    The streaming path has to strip the same thing or the two say different words — and this one
    cannot fix it afterwards, because a surface rendering fragment by fragment has already drawn the
    blank line by the time the lesson ends.
    """
    # Arrange
    model = StreamingModel(["\n\n", "   Picture the loss", " as a hillside."])

    # Act
    parts = [
        part
        async for part in ClaudeTutor("m", client=model).stream(
            _move(), _node(), topic="A subject", run_id="r1"
        )
    ]

    # Assert — nothing empty on the wire, and the first thing the learner sees is a word.
    assert parts == ["Picture the loss", " as a hillside."]


async def test_a_tutor_that_streams_nothing_fails_the_way_a_silent_one_does() -> None:
    """``SessionTurn.tutor`` is ``min_length=1``, so a wordless turn cannot be stored. Caught here,
    where the node can still be named, rather than as a validation error thrown out of session
    assembly with nothing to say about which turn produced it."""
    # Arrange
    tutor = ClaudeTutor("m", client=StreamingModel([]))

    # Act / Assert
    with pytest.raises(TutorUnavailableError):
        async for _ in tutor.stream(_move(), _node(), topic="A subject", run_id="r1"):
            pass


# ── the fragments reach the learner while the turn is still running ────────────────────────────


async def test_deltas_reach_the_learner_while_the_tutor_is_still_writing() -> None:
    """The task's RED assertion, and the one written so a buffering implementation cannot pass it.

    ``GatedTutor`` will not write its second fragment until the first has been relayed. A
    ``take_turn`` that gathered the whole turn before calling the sink therefore never gets a second
    fragment and never returns — so this fails on the deadlock, not on a shape assertion that a
    buffering implementation would satisfy just as well.
    """
    # Arrange
    tutor = GatedTutor()
    relayed: list[str] = []

    def sink(delta: str) -> None:
        relayed.append(delta)
        tutor.first_was_relayed.set()

    session = await _opened(StubTutor())

    # Act
    async with asyncio.timeout(_DEADLOCK_S):
        answered = await _answered(session, tutor, on_delta=sink)

    # Assert
    assert relayed == ["The first part. ", "The rest of it."]
    assert answered.turns[-1].tutor == "The first part. The rest of it."


async def test_what_was_relayed_is_what_the_turn_recorded() -> None:
    """A surface fed by the stream and a session re-read from the store must not be able to
    disagree about what the tutor said — a reload would then rewrite the lesson."""
    # Arrange
    relayed: list[str] = []
    session = await _opened(StubTutor())

    # Act
    answered = await _answered(session, StubTutor(), on_delta=relayed.append)

    # Assert
    assert "".join(relayed).strip() == answered.turns[-1].tutor
    assert len(relayed) > 1


async def test_a_sink_that_fails_does_not_cost_the_learner_their_turn() -> None:
    """A sink is a client's connection by another name, and clients disappear mid-turn. Letting that
    propagate would trade a paid-for turn for a lost animation — the same call Phase 1 made for the
    compile stream's progress sink."""

    # Arrange
    def sink(_delta: str) -> None:
        raise RuntimeError("the learner closed the tab")

    session = await _opened(StubTutor())

    # Act
    answered = await _answered(session, StubTutor(), on_delta=sink)

    # Assert — the turn happened, was taught, and was recorded.
    assert len(answered.turns) == len(session.turns) + 1
    assert answered.turns[-1].tutor


async def test_a_turn_taken_without_a_sink_is_p2as_turn_unchanged() -> None:
    """The streaming path is additive (U2). ``teach`` keeps its retry and its single call, and the
    REST endpoint keeps the contract P2a's suite is written against — so a turn with nobody
    listening must not quietly become a streamed one."""

    # Arrange
    class WholeOnlyTutor(StubTutor):
        async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[str]:
            raise AssertionError("a turn with no sink must not stream")
            yield ""  # pragma: no cover - unreachable, present to keep this a generator

    session = await _opened(StubTutor())

    # Act
    answered = await _answered(session, WholeOnlyTutor())

    # Assert
    assert answered.turns[-1].tutor
