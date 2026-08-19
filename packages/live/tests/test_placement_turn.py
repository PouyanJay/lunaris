"""The interview: what a placing session does with an answer (Lunaris Live, Phase 2c, T2).

T1 opened a session on a topic and asked the first question. This is the loop that reads the
answers: record what the learner said on the turn that asked it (never grade it, never move a
belief), then either ask the next question, or stop asking. It stops when the interviewer says it
has enough, when it has asked its bounded share, or when the map has landed (R3): the interview
absorbs the compile and never extends it. Once the map is there, the same answer that closes the
interview is answered with the first lesson, so the learner never sees a seam.

Two other endings: the map is not there yet when the interview runs out (``WARMING``, an honest
wait the surface polls through ``advance_placement``), and the compile has failed (the session
closes and says so, rather than interviewing forever for a map that will never come).
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import (
    DirectorMove,
    InterviewerUnavailableError,
    InterviewExchange,
    LearnerModel,
    MoveKind,
    NodePrior,
    PlacementResult,
    PriorMapperUnavailableError,
    Session,
    SessionStatus,
    SessionTurn,
    StaleAnswerError,
    StubInterviewer,
    StubPriorMapper,
    StubTutor,
    advance_placement,
    open_placement,
    take_placement_turn,
)


class ScriptedInterviewer:
    """Asks its questions in order and records every call; ``None`` once they run out."""

    def __init__(self, *questions: str) -> None:
        self._questions = list(questions)
        self.calls: list[tuple[InterviewExchange, ...]] = []

    async def ask(
        self,
        topic: str,
        *,
        exchanges: Sequence[InterviewExchange] = (),
        run_id: str,
    ) -> str | None:
        self.calls.append(tuple(exchanges))
        return self._questions[len(exchanges)] if len(exchanges) < len(self._questions) else None


class BrokenInterviewer:
    async def ask(self, topic: str, **kwargs: object) -> str | None:
        raise InterviewerUnavailableError("provider is down")


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id="g1",
        topic="Bayes' theorem",
        nodes=[
            ConceptNode(
                id="prior",
                name="Prior",
                definition="What you believed before.",
                mastery_criteria=[
                    MasteryCriterion(
                        kind=MasteryCriterionKind.EXPLAIN, statement="Say what a prior is."
                    )
                ],
            ),
            ConceptNode(
                id="update",
                name="Update",
                definition="How evidence moves it.",
                requires=["prior"],
                mastery_criteria=[
                    MasteryCriterion(
                        kind=MasteryCriterionKind.EXPLAIN, statement="Say how it moves."
                    )
                ],
            ),
        ],
        topo_order=["prior", "update"],
        is_acyclic=True,
    )


async def _placing(interviewer: object) -> Session:
    return await open_placement(
        "Bayes' theorem", graph_id="g1", session_id="s1", run_id="r1", interviewer=interviewer
    )


async def _answered(
    session: Session,
    interviewer: object,
    *,
    answer: str = "I did some statistics at school.",
    graph: ConceptGraph | None = None,
    failure: str | None = None,
    answering_seq: int | None = None,
    mapper: object | None = None,
):
    return await take_placement_turn(
        session,
        answer=answer,
        answering_seq=answering_seq if answering_seq is not None else session.turns[-1].seq,
        interviewer=interviewer,
        mapper=mapper or StubPriorMapper(),
        graph=graph,
        failure=failure,
        model=LearnerModel(graph_id="g1"),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=30.0,
        budget_s=1800.0,
    )


# ── the interview continues ─────────────────────────────────────────────────────────────────────


async def test_an_answer_is_recorded_on_the_question_that_asked_it_and_never_graded() -> None:
    interviewer = ScriptedInterviewer("Q1?", "Q2?")
    session = await _placing(interviewer)

    outcome = await _answered(session, interviewer, answer="A statistics course, years ago.")

    asked, next_turn = outcome.session.turns
    assert asked.answer == "A statistics course, years ago."
    assert asked.grade is None, "an interview answer is about the learner, not a criterion"
    assert next_turn.seq == 2
    assert next_turn.move.kind is MoveKind.PLACE
    assert next_turn.tutor == "Q2?"
    assert outcome.session.status is SessionStatus.PLACING
    # No belief moved: the model that came in is the model that goes out.
    assert outcome.model.nodes == {}


async def test_the_interviewer_is_told_the_whole_history_oldest_first() -> None:
    interviewer = ScriptedInterviewer("Q1?", "Q2?", "Q3?")
    session = await _placing(interviewer)
    session = (await _answered(session, interviewer, answer="A1")).session

    await _answered(session, interviewer, answer="A2")

    # Pinned by value: the whole history, oldest first, on the last call.
    exchanges = interviewer.calls[-1]
    assert [(e.question, e.answer) for e in exchanges] == [("Q1?", "A1"), ("Q2?", "A2")]


async def test_a_stale_answer_is_refused_before_anything_is_recorded() -> None:
    interviewer = ScriptedInterviewer("Q1?", "Q2?")
    session = await _placing(interviewer)
    session = (await _answered(session, interviewer)).session

    with pytest.raises(StaleAnswerError):
        await _answered(session, interviewer, answering_seq=1)


# ── the interview ends ──────────────────────────────────────────────────────────────────────────


async def test_the_interview_ends_warming_when_the_interviewer_has_enough_and_no_map() -> None:
    """``None`` from the interviewer with no map yet is the honest wait: WARMING, one last turn that
    says so and asks nothing, and the answer that ended it recorded where it belongs."""
    interviewer = ScriptedInterviewer("Q1?")
    session = await _placing(interviewer)

    outcome = await _answered(session, interviewer, answer="Only what I've read.")

    assert outcome.session.status is SessionStatus.WARMING
    asked, waiting = outcome.session.turns
    assert asked.answer == "Only what I've read."
    assert waiting.move.kind is MoveKind.PLACE
    assert waiting.criterion is None
    assert not waiting.tutor.rstrip().endswith("?"), "a warming turn asks nothing"
    assert "Bayes' theorem" in waiting.tutor


async def test_the_interview_is_bounded_even_when_the_interviewer_would_go_on() -> None:
    """An interviewer that always has one more question is bounded by the loop, not by itself:
    four exchanges is the most a compile's worth of waiting should cost a learner (A2)."""
    interviewer = ScriptedInterviewer(*[f"Q{i}?" for i in range(1, 20)])
    session = await _placing(interviewer)
    for i in range(1, 5):
        outcome = await _answered(session, interviewer, answer=f"A{i}")
        session = outcome.session

    assert session.status is SessionStatus.WARMING
    exchanges = [(t.tutor, t.answer) for t in session.turns if t.answer is not None]
    assert len(exchanges) == 4
    # Asked once per open question, and NOT for a fifth: the bound is checked before the ask.
    assert len(interviewer.calls) == 4


async def test_when_the_map_has_landed_the_answer_is_met_with_the_first_lesson() -> None:
    """The seam the learner never sees: the answer that closes the interview is answered with the
    first teaching turn, on the map, from the director's own first move (R3)."""
    interviewer = ScriptedInterviewer("Q1?", "Q2?", "Q3?")
    session = await _placing(interviewer)
    calls_before = len(interviewer.calls)

    outcome = await _answered(session, interviewer, answer="A1", graph=_graph())

    assert outcome.session.status is SessionStatus.ACTIVE
    asked, lesson = outcome.session.turns
    assert asked.answer == "A1"
    assert lesson.seq == 2
    # The director's move on this map with nothing known: introduce the root, "prior".
    assert (lesson.move.kind, lesson.move.node_id) == (MoveKind.INTRODUCE, "prior")
    assert lesson.criterion is not None, "a lesson stages something; an interview turn never did"
    assert "Prior" in lesson.tutor
    # The interviewer was NOT asked again: the map landing ends the interview at this answer.
    assert len(interviewer.calls) == calls_before


async def test_a_compile_that_failed_closes_the_session_and_says_so() -> None:
    interviewer = ScriptedInterviewer("Q1?", "Q2?")
    session = await _placing(interviewer)

    outcome = await _answered(
        session, interviewer, answer="A1", failure="The model gave up on this topic."
    )

    assert outcome.session.status is SessionStatus.CLOSED
    asked, goodbye = outcome.session.turns
    assert asked.answer == "A1", "what the learner said is kept even when the map is not"
    assert goodbye.move.kind is MoveKind.CLOSE
    assert "The model gave up on this topic." in goodbye.tutor
    assert "Bayes' theorem" in goodbye.tutor


async def test_the_compilers_reason_is_made_a_sentence_of_its_own_in_the_goodbye() -> None:
    """The real compiler raises log-style fragments ("could not decompose 'X' into concepts");
    dropped verbatim between two sentences they read as a run-on (found in review)."""
    session = await _placing(ScriptedInterviewer("Q1?"))

    outcome = await _answered(
        session, ScriptedInterviewer(), answer="A1", failure="could not decompose 'X' into concepts"
    )

    goodbye = outcome.session.turns[-1].tutor
    assert "today. Could not decompose 'X' into concepts. Start again" in goodbye


async def test_an_interviewer_that_cannot_speak_ends_the_interview_rather_than_the_turn() -> None:
    """The interview is a nicety and the compile is the substance: a provider that is down for the
    next question must not cost the learner the answer they just gave, or the session."""
    session = await _placing(ScriptedInterviewer("Q1?"))

    outcome = await _answered(session, BrokenInterviewer(), answer="A1")

    assert outcome.session.status is SessionStatus.WARMING
    assert outcome.session.turns[0].answer == "A1"


async def test_an_interviewer_that_cannot_open_still_opens_with_a_question() -> None:
    """Same reasoning at the door: by the time the interviewer is asked, the compile has been
    launched. A session that failed to open would leave a compile running for nobody."""
    session = await open_placement(
        "Bayes' theorem",
        graph_id="g1",
        session_id="s1",
        run_id="r1",
        interviewer=BrokenInterviewer(),
    )

    assert session.status is SessionStatus.PLACING
    assert session.turns[0].tutor.endswith("?")
    assert "Bayes' theorem" in session.turns[0].tutor


# ── warming, and the way out of it ──────────────────────────────────────────────────────────────


async def _warming() -> Session:
    interviewer = ScriptedInterviewer("Q1?")
    session = await _placing(interviewer)
    outcome = await _answered(session, interviewer, answer="A1")
    assert outcome.session.status is SessionStatus.WARMING
    return outcome.session


async def _advanced(
    session: Session,
    *,
    graph: ConceptGraph | None,
    failure: str | None = None,
    mapper: object | None = None,
):
    return await advance_placement(
        session,
        mapper=mapper or StubPriorMapper(),
        graph=graph,
        failure=failure,
        model=LearnerModel(graph_id="g1"),
        tutor=StubTutor(),
        run_id="r3",
        elapsed_s=60.0,
        budget_s=1800.0,
    )


async def test_advancing_a_warming_session_whose_map_is_still_not_there_changes_nothing() -> None:
    session = await _warming()

    outcome = await _advanced(session, graph=None)

    assert outcome is None, "nothing to do yet is a distinct answer, not a turn"


async def test_advancing_a_warming_session_whose_map_has_landed_starts_teaching() -> None:
    session = await _warming()

    outcome = await _advanced(session, graph=_graph())

    assert outcome is not None
    assert outcome.session.status is SessionStatus.ACTIVE
    lesson = outcome.session.turns[-1]
    assert (lesson.move.kind, lesson.move.node_id) == (MoveKind.INTRODUCE, "prior")
    assert lesson.seq == len(session.turns) + 1


async def test_advancing_a_warming_session_whose_compile_failed_closes_it() -> None:
    session = await _warming()

    outcome = await _advanced(session, graph=None, failure="Ran out of time.")

    assert outcome is not None
    assert outcome.session.status is SessionStatus.CLOSED
    assert "Ran out of time." in outcome.session.turns[-1].tutor


async def test_an_answer_into_a_warming_session_is_stale_because_nothing_is_asked() -> None:
    """A warming session's last turn asks nothing, and the one before it is already answered, so
    an answer naming either is an answer to a question that has been dealt with (P2a AD23)."""
    session = await _warming()

    with pytest.raises(StaleAnswerError):
        await _answered(session, ScriptedInterviewer(), answer="More?")


async def test_advancing_a_session_that_is_not_warming_is_a_caller_error() -> None:
    active = Session(
        session_id="s1",
        graph_id="g1",
        status=SessionStatus.ACTIVE,
        started_at=datetime(2026, 8, 19, 9, 0, tzinfo=UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="prior", reason="Root."),
                tutor="Prior.",
                run_id="r1",
            )
        ],
    )
    with pytest.raises(ValueError):
        await _advanced(active, graph=_graph())


# ── the offline interviewer ─────────────────────────────────────────────────────────────────────


async def test_the_stub_interviewer_carries_a_whole_placement_offline() -> None:
    """`make run` without a key: three questions, then enough. Pinned so the offline surface has an
    interview to show, and so its bound is inside the loop's."""
    interviewer = StubInterviewer()
    session = await _placing(interviewer)
    for i in range(3):
        outcome = await _answered(session, interviewer, answer=f"A{i}")
        session = outcome.session

    assert session.status is SessionStatus.WARMING
    assert len([t for t in session.turns if t.answer is not None]) == 3


# ── the priors, at the seam (T3) ─────────────────────────────────────────────────────────────────


class ScriptedMapper:
    def __init__(self, result: PlacementResult) -> None:
        self._result = result
        self.calls: list[tuple[str, tuple[InterviewExchange, ...], str]] = []

    async def map(self, topic, exchanges, graph, *, run_id):
        self.calls.append((topic, tuple(exchanges), graph.graph_id))
        return self._result


class BrokenMapper:
    async def map(self, topic, exchanges, graph, *, run_id):
        raise PriorMapperUnavailableError("provider is down")


async def test_when_the_map_lands_the_interview_is_mapped_to_priors_and_a_profile() -> None:
    """The seam that makes the interview mean something: the mapper reads the whole exchange and
    the map, its priors seed the model the director reads for the FIRST lesson, and its profile
    rides the session for the tutor. A learner who claims the root is verified on it, not taught."""
    mapper = ScriptedMapper(
        PlacementResult(
            profile="Did statistics at school; wants to read papers.",
            priors=[NodePrior(node_id="prior", prior=0.8)],
        )
    )
    interviewer = ScriptedInterviewer("Q1?", "Q2?")
    session = await _placing(interviewer)

    outcome = await _answered(session, interviewer, answer="A1", graph=_graph(), mapper=mapper)

    # The mapper saw the whole exchange, on this map.
    ((topic, exchanges, graph_id),) = mapper.calls
    assert topic == "Bayes' theorem" and graph_id == "g1"
    assert [(e.question, e.answer) for e in exchanges] == [("Q1?", "A1")]
    # The prior reached the model the director read: the first lesson VERIFIES the claimed root
    # rather than introducing it.
    assert outcome.model.nodes["prior"].prior == 0.8
    lesson = outcome.session.turns[-1]
    assert (lesson.move.kind, lesson.move.node_id) == (MoveKind.RETRIEVE, "prior")
    assert outcome.session.profile == "Did statistics at school; wants to read papers."


async def test_the_warming_seam_is_mapped_too() -> None:
    """The other way a placement reaches its map: the interview ran out first and a poll finds it.
    Found in review: this seam was exercised only with the offline mapper on an answer it could not
    credit, so a build that dropped the mapper here stayed green."""
    mapper = ScriptedMapper(
        PlacementResult(profile="Knows priors.", priors=[NodePrior(node_id="prior", prior=0.8)])
    )
    session = await _warming()

    outcome = await _advanced(session, graph=_graph(), mapper=mapper)

    assert outcome is not None
    assert len(mapper.calls) == 1
    assert outcome.model.nodes["prior"].prior == 0.8
    assert outcome.session.profile == "Knows priors."
    lesson = outcome.session.turns[-1]
    assert (lesson.move.kind, lesson.move.node_id) == (MoveKind.RETRIEVE, "prior")


async def test_a_mapper_that_cannot_speak_places_nobody_and_teaching_still_begins() -> None:
    interviewer = ScriptedInterviewer("Q1?", "Q2?")
    session = await _placing(interviewer)

    outcome = await _answered(
        session, interviewer, answer="A1", graph=_graph(), mapper=BrokenMapper()
    )

    assert outcome.session.status is SessionStatus.ACTIVE
    assert outcome.model.nodes == {}
    assert outcome.session.profile is None
    lesson = outcome.session.turns[-1]
    assert (lesson.move.kind, lesson.move.node_id) == (MoveKind.INTRODUCE, "prior")


async def test_the_mapper_is_not_asked_when_the_map_never_came() -> None:
    mapper = ScriptedMapper(PlacementResult(profile="x", priors=[]))
    session = await _placing(ScriptedInterviewer("Q1?"))

    await _answered(session, ScriptedInterviewer(), answer="A1", failure="Gone.", mapper=mapper)

    assert mapper.calls == []
