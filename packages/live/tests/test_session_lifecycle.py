"""A session's life: its clock, its ending, and answering the turn you were actually shown (T6).

T5 made the loop turn; this makes it a *session* — something with a beginning, a bounded middle and
a deliberate end that a learner can read. Three claims live here:

- The clock is wall time measured from when the session opened, so it survives a reload. Measured in
  turns it would let a session of long, slow turns run for hours (AD9); held in the process it would
  reset every time the tab did.
- The close is a turn, not just a status. A session that ended by going silent is indistinguishable
  from one that crashed, and `status` is not something a transcript shows.
- An answer names the turn it is answering. Otherwise a double-submit answers the *next* question
  with the previous question's words, and neither the learner nor the trace can tell.
"""

import pytest
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    TeachingSpec,
)
from lunaris_live.session import (
    LearnerModel,
    MoveKind,
    SessionClock,
    SessionStatus,
    StaleAnswerError,
    StubGrader,
    StubTutor,
    open_session,
    take_turn,
)

_BUDGET_S = 1800.0


def _node(node_id: str, name: str, *, requires: list[str] | None = None) -> ConceptNode:
    return ConceptNode(
        id=node_id,
        name=name,
        definition=f"What {name} is.",
        requires=requires or [],
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
        nodes=[_node("a", "Alpha"), _node("b", "Beta", requires=["a"])],
        topo_order=["a", "b"],
        is_acyclic=True,
    )


async def _opened():
    return (
        await open_session(
            _graph(),
            LearnerModel(graph_id="g1"),
            SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
            session_id="s1",
            run_id="r1",
            tutor=StubTutor(),
        )
    ).session


async def _answer(
    session, *, answer: str = "No idea.", elapsed_s: float = 10.0, seq: int | None = None
):
    return await take_turn(
        session,
        _graph(),
        LearnerModel(graph_id="g1"),
        answer=answer,
        answering_seq=session.turns[-1].seq if seq is None else seq,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=elapsed_s,
        budget_s=_BUDGET_S,
    )


# ── the clock ──────────────────────────────────────────────────────────────────────────────────


async def test_a_session_records_when_it_began() -> None:
    """The budget is wall time (plan §6, AD9), and wall time cannot be recovered from the turns —
    so the one thing a resumed session needs in order to know how long it has left is stamped when
    it opens and carried in the row."""
    # Act
    session = await _opened()

    # Assert
    assert session.started_at is not None
    assert session.started_at.tzinfo is not None, (
        "a naive timestamp cannot be compared across hosts"
    )


async def test_a_session_past_its_budget_closes_on_the_next_answer() -> None:
    """The clock rule the director has always had, now reachable: before this, ``elapsed_s`` was
    hardcoded to zero, so the budget was a setting nothing could ever hit."""
    # Act — the learner answers well past the session's whole budget.
    outcome = await _answer(await _opened(), elapsed_s=_BUDGET_S + 1)

    # Assert
    assert outcome.session.status is SessionStatus.CLOSED
    assert outcome.session.turns[-1].move.kind is MoveKind.CLOSE


async def test_a_session_inside_its_budget_keeps_going() -> None:
    """The boundary in the other direction, so the rule above is a rule and not a constant."""
    # Act
    outcome = await _answer(await _opened(), elapsed_s=1.0)

    # Assert
    assert outcome.session.status is SessionStatus.ACTIVE


# ── the ending ─────────────────────────────────────────────────────────────────────────────────


async def test_a_closed_session_ends_on_something_the_learner_can_read() -> None:
    """A session that ends by going quiet is indistinguishable from one that crashed. ``status`` is
    a field; the transcript is what the learner sees, so the ending has to be in the transcript.

    The recap, the mastery delta and the spaced-retrieval schedule are P2c's ceremony. What T6 owes
    is that the session says goodbye at all, and says why it is ending.
    """
    # Act
    outcome = await _answer(await _opened(), elapsed_s=_BUDGET_S + 1)

    # Assert
    closing = outcome.session.turns[-1]
    assert closing.move.kind is MoveKind.CLOSE
    assert closing.tutor.strip()
    assert closing.criterion is None, "a closing turn asks for nothing — nothing follows it"
    assert closing.run_id == "r2"


async def test_the_answered_turn_survives_the_ending() -> None:
    """The last thing the learner did still has to be in the record they scrolled back through."""
    # Act
    outcome = await _answer(await _opened(), answer="No idea.", elapsed_s=_BUDGET_S + 1)

    # Assert — the answered turn, then the goodbye.
    answered = outcome.session.turns[-2]
    assert answered.answer == "No idea."
    assert answered.grade is not None


async def test_a_close_is_the_last_word() -> None:
    """Nothing may follow it: the session is closed, and ``take_turn`` refuses a closed session."""
    # Arrange
    closed = (await _answer(await _opened(), elapsed_s=_BUDGET_S + 1)).session

    # Act / Assert
    with pytest.raises(Exception) as refused:
        await _answer(closed)
    assert "closed" in str(refused.value)


# ── answering the turn you were shown ──────────────────────────────────────────────────────────


async def test_an_answer_names_the_turn_it_is_answering() -> None:
    """The happy path, so the guard below is a guard and not a wall."""
    # Act
    outcome = await _answer(await _opened(), seq=1)

    # Assert
    assert outcome.session.turns[0].answer == "No idea."


async def test_an_answer_to_a_question_that_has_moved_on_is_refused() -> None:
    """A learner pressing send twice, or a tab left open while another one answered. Without this
    the second copy is graded against the *next* question — the words are recorded under a criterion
    they were never written for, and the belief that moves is about the wrong concept."""
    # Arrange — one answer has already been given, so the session is on turn 2.
    session = (await _answer(await _opened(), seq=1)).session

    # Act / Assert — the same submit arriving again, still naming turn 1.
    with pytest.raises(StaleAnswerError):
        await _answer(session, seq=1)


async def test_a_refused_answer_changes_nothing() -> None:
    """The point of refusing is that the learner can be told and can retry; a partial application
    would leave a belief moved by an answer the session never accepted."""
    # Arrange
    session = (await _answer(await _opened(), seq=1)).session
    before = session.model_dump(mode="json")

    # Act
    with pytest.raises(StaleAnswerError):
        await _answer(session, seq=1)

    # Assert
    assert session.model_dump(mode="json") == before
