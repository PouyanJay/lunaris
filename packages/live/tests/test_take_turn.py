"""The loop closing: an answer becomes evidence, and evidence changes what happens next (T5).

Until now the learner model was something only tests filled in. This is where the loop actually
turns: the learner answers the criterion the last turn staged, the grader scores it, the belief
moves, and the director reads the moved belief to pick the next move. The RED assertion for the
task is the third of those — a wrong answer lowers the estimate for *that* concept and no other.

The tutor and grader here are deterministic stubs; what is under test is the wiring of a turn, not
the quality of teaching or judging.
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
    EvidenceKind,
    GraderUnavailableError,
    LayoutComponent,
    LearnerModel,
    MoveKind,
    Session,
    SessionClock,
    SessionClosedError,
    SessionStatus,
    StubGrader,
    StubTutor,
    TutorUnavailableError,
    open_session,
    recall_of,
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
                kind=MasteryCriterionKind.EXPLAIN,
                statement=f"Explain {name} in your own words.",
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


async def _opened() -> Session:
    return await open_session(
        _graph(),
        LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )


async def _answered(answer: str, *, model: LearnerModel | None = None):
    return await take_turn(
        await _opened(),
        _graph(),
        model or LearnerModel(graph_id="g1"),
        answer=answer,
        answering_seq=1,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )


# ── the criterion the learner was asked to meet ────────────────────────────────────────────────


async def test_the_opening_turn_stages_something_the_learner_can_be_scored_on() -> None:
    """Without a staged criterion there is nothing to grade, so the loop cannot turn at all: the
    tutor talks, the learner answers, and no belief ever moves."""
    # Act
    session = await _opened()

    # Assert
    staged = session.turns[0].criterion
    assert staged is not None
    assert staged.statement == "Explain Alpha in your own words."


async def test_the_criterion_the_learner_met_is_kept_on_the_turn_itself() -> None:
    """Not looked up from the map afterwards. C1 lets the map change mid-session, so a transcript
    that pointed at a node id would be able to misreport what somebody was actually asked."""
    # Act
    outcome = await _answered("Explain Alpha in your own words: it is what Alpha is.")

    # Assert
    answered = outcome.session.turns[0]
    assert answered.criterion is not None
    assert answered.answer == "Explain Alpha in your own words: it is what Alpha is."
    assert answered.grade is not None


# ── the RED assertion: evidence moves one belief ───────────────────────────────────────────────


async def test_a_wrong_answer_lowers_the_estimate_for_that_concept_and_no_other() -> None:
    # Act
    outcome = await _answered("No idea, sorry.")

    # Assert — the concept that was asked about moved down to where a miss puts it (a fresh belief
    # pulled towards 0.0), and nothing else acquired a belief at all. Pinned to the value rather
    # than to "below the mastery bar": a NOT_MET target of 0.4 would still be under any loose bound
    # while quietly meaning a wrong answer teaches the system something.
    moved = outcome.model.nodes["a"]
    assert moved.estimate == pytest.approx(0.0)
    assert moved.evidence_count == 1
    assert set(outcome.model.nodes) == {"a"}


async def test_a_good_answer_raises_the_estimate_for_that_concept() -> None:
    # Act
    outcome = await _answered("I can explain Alpha: it is what Alpha is.")

    # Assert
    assert outcome.session.turns[0].grade is not None
    assert outcome.session.turns[0].grade.kind is EvidenceKind.MET
    assert recall_of(outcome.model, "a", at_turn=1) > 0.0


async def test_the_grade_the_learner_reads_is_the_one_the_belief_was_moved_by() -> None:
    """Two records of one judgement is how a transcript comes to disagree with the model behind
    it — the learner told they passed while the director acts as though they did not."""
    # Act
    outcome = await _answered("No idea, sorry.")

    # Assert
    grade = outcome.session.turns[0].grade
    assert grade is not None
    assert grade.kind is EvidenceKind.NOT_MET
    assert outcome.model.nodes["a"].estimate < 0.5


# ── and the loop turns ─────────────────────────────────────────────────────────────────────────


async def test_the_answer_is_followed_by_the_next_turn() -> None:
    """A loop that graded and stopped would be a quiz. The point of the model moving is that the
    director reads it and decides again."""
    # Act
    outcome = await _answered("No idea, sorry.")

    # Assert
    assert [turn.seq for turn in outcome.session.turns] == [1, 2]
    assert outcome.session.turns[1].run_id == "r2"
    assert outcome.session.turns[1].tutor.strip()


async def test_a_learner_who_keeps_missing_is_not_marched_onward() -> None:
    """The director's stuck rule, reached through the real loop rather than a hand-built model: two
    misses on the concept in front of them and the next move is remediation, not new material."""
    # Arrange
    first = await _answered("No idea, sorry.")

    # Act — the same shrug again, against the belief the first one left.
    second = await take_turn(
        first.session,
        _graph(),
        first.model,
        answer="Still no idea.",
        answering_seq=first.session.turns[-1].seq,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id="r3",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Assert
    assert second.session.turns[-1].move.kind is MoveKind.REMEDIATE
    assert second.session.turns[-1].move.node_id == "a"


async def test_a_map_with_nothing_left_to_teach_closes_rather_than_looping() -> None:
    """The last thing a session should do is keep talking after it has run out of material."""
    # Arrange — a one-concept map, answered well enough to master.
    single = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[_node("a", "Alpha")],
        topo_order=["a"],
        is_acyclic=True,
    )
    session = await open_session(
        single,
        LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )
    model = LearnerModel(graph_id="g1")

    # Act — answer well until the director has nothing left to introduce.
    for index in range(4):
        outcome = await take_turn(
            session,
            single,
            model,
            answer="I can explain Alpha: it is what Alpha is.",
            answering_seq=session.turns[-1].seq,
            grader=StubGrader(),
            tutor=StubTutor(),
            run_id=f"r{index + 2}",
            elapsed_s=0.0,
            budget_s=_BUDGET_S,
        )
        session, model = outcome.session, outcome.model
        if session.status is SessionStatus.CLOSED:
            break

    # Assert — closed, ending on the goodbye, with the answered turn still behind it (T6 makes the
    # ending a turn the learner can read rather than a status change they cannot see).
    assert session.status is SessionStatus.CLOSED
    assert session.turns[-1].move.kind is MoveKind.CLOSE
    assert session.turns[-2].answer is not None

    # The goodbye is laid out too (P2b T5). Asserted at the *call site* rather than only against
    # the composer, because the close branch builds its own turn: it names no concept and asks the
    # tutor for nothing, so it is the one path where "every turn has a layout" could quietly stop
    # being true and leave a renderer holding a turn it has a second way to draw.
    goodbye = session.turns[-1].layout
    assert goodbye is not None
    assert [block.component for block in goodbye.blocks] == [
        LayoutComponent.STACK,
        LayoutComponent.PROSE,
        LayoutComponent.SURFACE,
    ]


# ── the tutor is told what it has already said ─────────────────────────────────────────────────


async def test_the_tutor_is_handed_what_it_already_said_about_this_concept() -> None:
    """And nothing it said about another one. Passing the whole session would spend the prompt on
    material the learner is not being taught, and passing nothing is what let a remediation come
    back as the introduction repeated word for word."""

    # Arrange — a spy that answers differently each time, so history and repetition are visible.
    class SpyTutor:
        def __init__(self) -> None:
            self.histories: list[tuple[str, list[str]]] = []

        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ) -> str:
            self.histories.append((node.id, list(already_said)))
            return f"Teaching {node.name} #{len(self.histories)}."

    tutor = SpyTutor()
    session = await open_session(
        _graph(),
        LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id="s1",
        run_id="r1",
        tutor=tutor,
    )

    # Act — one wrong answer, so the director stays on the same concept.
    outcome = await take_turn(
        session,
        _graph(),
        LearnerModel(graph_id="g1"),
        answer="No idea, sorry.",
        answering_seq=1,
        grader=StubGrader(),
        tutor=tutor,
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Act again — answer well twice so the session masters "a" and moves to "b".
    for index, reply in enumerate(["I can explain Alpha: it is what Alpha is."] * 2):
        outcome = await take_turn(
            outcome.session,
            _graph(),
            outcome.model,
            answer=reply,
            answering_seq=outcome.session.turns[-1].seq,
            grader=StubGrader(),
            tutor=tutor,
            run_id=f"r{index + 3}",
            elapsed_s=0.0,
            budget_s=_BUDGET_S,
        )

    # Assert — the first turn had nothing behind it; the second was handed exactly what had been
    # said about "a"; and the turn that moved on to "b" was handed NOTHING, because none of the
    # words spoken about "a" are words this tutor has already used on "b".
    assert tutor.histories[0] == ("a", [])
    assert tutor.histories[1] == ("a", ["Teaching Alpha #1."])
    moved_on = next((concept, said) for concept, said in tutor.histories if concept == "b")
    assert moved_on == ("b", [])


# ── when the loop cannot turn at all ───────────────────────────────────────────────────────────


async def test_a_grader_that_cannot_answer_moves_nothing() -> None:
    """The failure U1's whole design exists to survive. An outage must not read as a wrong answer:
    the belief the director gates progress on would move against a learner for a bad minute on the
    provider's side, and the turn would be recorded as scored when nothing scored it."""

    class BrokenGrader:
        async def grade(self, answer, *, criterion, node, run_id):
            raise GraderUnavailableError("provider is down")

    # Arrange
    session = await _opened()
    model = LearnerModel(graph_id="g1")

    # Act / Assert — it propagates rather than degrading into evidence...
    with pytest.raises(GraderUnavailableError):
        await take_turn(
            session,
            _graph(),
            model,
            answer="A real attempt at an answer.",
            answering_seq=session.turns[-1].seq,
            grader=BrokenGrader(),
            tutor=StubTutor(),
            run_id="r2",
            elapsed_s=0.0,
            budget_s=_BUDGET_S,
        )

    # ... and nothing the caller holds has changed, so a retry means what the learner expects.
    assert model.nodes == {}
    assert session.turns[-1].answer is None
    assert session.turns[-1].grade is None


async def test_a_tutor_that_cannot_speak_mid_session_moves_nothing_either() -> None:
    """The answer was graded before the tutor was asked, so this is the one path where a failure
    could half-happen: a belief moved for a turn the learner never receives. Nothing is returned,
    so nothing is persisted, and the same answer can be sent again."""

    class SilentTutor:
        async def teach(
            self, move, node, *, topic, criterion=None, already_said=(), profile=None, run_id
        ):
            raise TutorUnavailableError("provider is down")

    # Arrange
    session = await _opened()
    model = LearnerModel(graph_id="g1")

    # Act / Assert
    with pytest.raises(TutorUnavailableError):
        await take_turn(
            session,
            _graph(),
            model,
            answer="No idea, sorry.",
            answering_seq=session.turns[-1].seq,
            grader=StubGrader(),
            tutor=SilentTutor(),
            run_id="r2",
            elapsed_s=0.0,
            budget_s=_BUDGET_S,
        )
    assert model.nodes == {}
    assert session.turns[-1].answer is None


# ── answering something that cannot be answered ────────────────────────────────────────────────


async def test_a_closed_session_does_not_take_another_turn() -> None:
    """A learner with a stale tab must not be able to reopen a session the director ended —
    reopening it would run the session past the bound the close was there to enforce."""
    # Arrange
    closed = (await _opened()).model_copy(update={"status": SessionStatus.CLOSED})

    # Act / Assert
    with pytest.raises(SessionClosedError):
        await take_turn(
            closed,
            _graph(),
            LearnerModel(graph_id="g1"),
            answer="Anything.",
            answering_seq=closed.turns[-1].seq,
            grader=StubGrader(),
            tutor=StubTutor(),
            run_id="r2",
            elapsed_s=0.0,
            budget_s=_BUDGET_S,
        )


async def test_a_turn_that_asked_nothing_gradeable_still_moves_the_session_on() -> None:
    """A concept whose only criteria need a simulator (Phase 3) stages nothing, so there is nothing
    to score. The answer is still part of the transcript and the session still advances — refusing
    it would strand the learner on a concept the map cannot yet check."""
    # Arrange — a map whose one concept can only be demonstrated in a sim.
    sim_only = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[
            ConceptNode(
                id="a",
                name="Alpha",
                definition="What Alpha is.",
                mastery_criteria=[
                    MasteryCriterion(
                        kind=MasteryCriterionKind.MANIPULATE,
                        statement="Drive the rate up until it diverges.",
                        needs_sim=True,
                    )
                ],
            )
        ],
        topo_order=["a"],
        is_acyclic=True,
    )
    session = await open_session(
        sim_only,
        LearnerModel(graph_id="g1"),
        SessionClock(turn=1, elapsed_s=0.0, budget_s=_BUDGET_S),
        session_id="s1",
        run_id="r1",
        tutor=StubTutor(),
    )
    assert session.turns[0].criterion is None

    # Act
    outcome = await take_turn(
        session,
        sim_only,
        LearnerModel(graph_id="g1"),
        answer="I think it blows up.",
        answering_seq=1,
        grader=StubGrader(),
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Assert — recorded, ungraded, and no belief invented from an unscored answer.
    assert outcome.session.turns[0].answer == "I think it blows up."
    assert outcome.session.turns[0].grade is None
    assert outcome.model.nodes == {}
