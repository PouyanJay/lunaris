"""A picked option is marked by recognition, on the server, and never by the prose grader (T1).

The defect this pins was found in the first real browser session of Lunaris Live. A learner was
shown a quiz card, picked the true option, and was told they were wrong, four times over. The
cause is that whatever a card collects is handed to the prose grader and marked against the
criterion the turn staged, and a quiz's true option is the concept's ``definition`` verbatim
while the staged criterion asks the learner to *explain the mechanism in their own words*. So
the correct pick arrives as the exact text the grader has already refused as "you restated the
definition", scores NOT_MET, and pushes ``p_known`` down for a learner who demonstrably knows
the thing. Plan §8's stated fear, "a broken assessment surface corrupts data", happening in
production.

What is under test is the marking, not the teaching: the grader here is a spy that always
refuses, standing in for the real one, so "the grader was never asked" is an assertion rather
than a hope.
"""

from datetime import UTC, datetime

import pytest
from lunaris_live.graph import (
    ConceptGraph,
    ConceptNode,
    MasteryCriterion,
    MasteryCriterionKind,
    TeachingSpec,
)
from lunaris_live.session import (
    MAX_ANSWER_CHARS,
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    QuizCard,
    Session,
    SessionTurn,
    StubTutor,
    TurnGrade,
    apply_evidence,
    take_turn,
)

_BUDGET_S = 1800.0

#: The concept's own words. This is the string a quiz card offers as its true option, and the string
#: the learner sends back when they pick it.
_DEFINITION = "Alpha adjusts many small numbers until its guesses come out right."

#: Authored "as the learner would believe them" by the Phase 1 compiler.
_MISCONCEPTIONS = [
    "Alpha is programmed with explicit if-then rules by a developer.",
    "Alpha knows the answer the moment it is built; nothing is adjusted.",
]

#: The staged criterion, and the whole reason the pick cannot be marked against it: it asks for
#: production, and the true option is a definition. Word for word the shape the live session had.
_STATEMENT = "Explain in your own words how Alpha turns an input into an output."


class _RefusingGrader:
    """A grader that refuses everything, and counts how often it was asked to.

    It refuses with the real grader's own words from the live session, so a test that lets the pick
    reach it fails the way the learner's session did rather than in some abstract way.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def grade(
        self,
        answer: str,
        *,
        criterion: MasteryCriterion,
        node: ConceptNode,
        run_id: str,
        previously: object = (),
    ) -> TurnGrade:
        self.calls += 1
        return TurnGrade(
            kind=EvidenceKind.NOT_MET,
            reason="You restated the concept definition rather than explaining how it works.",
        )


def _node() -> ConceptNode:
    return ConceptNode(
        id="a",
        name="Alpha",
        definition=_DEFINITION,
        requires=[],
        teaching_spec=TeachingSpec(objective="Use Alpha.", misconceptions=list(_MISCONCEPTIONS)),
        mastery_criteria=[
            MasteryCriterion(kind=MasteryCriterionKind.EXPLAIN, statement=_STATEMENT)
        ],
    )


def _graph() -> ConceptGraph:
    return ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[_node()],
        topo_order=["a"],
        is_acyclic=True,
    )


def _quizzed() -> Session:
    """A session sitting on a quiz card, which is where a remediated learner actually sits."""
    return Session(
        session_id="s1",
        graph_id="g1",
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(
                    kind=MoveKind.REMEDIATE,
                    node_id="a",
                    reason="Alpha is not landing; showing the wrong models they might hold.",
                ),
                tutor="Which of these is actually true?",
                run_id="r1",
                criterion=MasteryCriterion(kind=MasteryCriterionKind.EXPLAIN, statement=_STATEMENT),
                surface=QuizCard(
                    node_id="a",
                    concept="Alpha",
                    question="Which of these is actually true about Alpha?",
                    options=[*_MISCONCEPTIONS, _DEFINITION],
                ),
            )
        ],
    )


async def _took(session: Session, answer: str, *, model: LearnerModel | None = None):
    """One turn on a caller-supplied session, with a grader that refuses and counts."""
    grader = _RefusingGrader()
    outcome = await take_turn(
        session,
        _graph(),
        model or LearnerModel(graph_id="g1"),
        answer=answer,
        answering_seq=1,
        grader=grader,
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )
    return outcome, grader


async def _picked(option: str, *, model: LearnerModel | None = None):
    grader = _RefusingGrader()
    outcome = await take_turn(
        _quizzed(),
        _graph(),
        model or LearnerModel(graph_id="g1"),
        answer=option,
        answering_seq=1,
        grader=grader,
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )
    return outcome, grader


# ── the RED assertion: the true option is never marked wrong ────────────────────────────────────


async def test_picking_the_true_option_is_not_marked_wrong() -> None:
    """The defect, stated as the learner met it. Everything else in this file is why."""
    # Act
    outcome, _ = await _picked(_DEFINITION)

    # Assert
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is not EvidenceKind.NOT_MET


async def test_a_pick_is_marked_without_asking_the_grader() -> None:
    """Deterministic rendering is mandatory in this tier (plan §8) and marking is the half that
    feeds the learner model. A model call to decide whether a picked string equals an authored
    string is a way for the answer to come out differently on two runs, and it is also a model call
    nobody needs to pay for."""
    # Act
    _, grader = await _picked(_DEFINITION)

    # Assert
    assert grader.calls == 0


async def test_recognition_is_partial_and_never_mastery() -> None:
    """U1. Picking the truth out of a lineup is real evidence and weaker evidence than saying it:
    ``select_surface`` already refuses a card with options for a RETRIEVE move on exactly this
    ground. PARTIAL keeps it under ``MASTERED``, so recognition can never unlock a dependent."""
    # Act
    outcome, _ = await _picked(_DEFINITION)

    # Assert
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.PARTIAL


async def test_a_correct_pick_moves_the_belief_up_not_down() -> None:
    """The corruption, measured. A learner who has missed twice sits low; the pick must climb out
    of the hole rather than deepen it."""
    # Arrange: where two misses leave somebody.
    stuck = LearnerModel(graph_id="g1")
    stuck = apply_evidence(stuck, "a", EvidenceKind.NOT_MET, at_turn=1)
    stuck = apply_evidence(stuck, "a", EvidenceKind.NOT_MET, at_turn=2)
    before = stuck.nodes["a"].estimate

    # Act
    outcome, _ = await _picked(_DEFINITION, model=stuck)

    # Assert
    assert outcome.model.nodes["a"].estimate > before


# ── a wrong pick is still worth something: which wrong model they hold ───────────────────────────


async def test_picking_a_misconception_is_not_met_and_names_the_one_they_hold() -> None:
    """Misconceptions are first-class entries in the learner model (plan §10), and the director's
    remediation keys off *which* wrong model somebody has. A card that authored three wrong answers
    and reported only "wrong" would throw that away at the one moment it is knowable exactly."""
    # Act
    outcome, grader = await _picked(_MISCONCEPTIONS[0])

    # Assert
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.NOT_MET
    assert grader.calls == 0
    assert _MISCONCEPTIONS[0] in graded.reason


# ── prose is still prose ─────────────────────────────────────────────────────────────────────────


async def test_typed_prose_that_matches_no_option_still_reaches_the_grader() -> None:
    """The composer stays open while a card stands (P2b T10), so a learner can write instead of
    picking. Only an exact option match is a pick; anything else is an answer and gets judged like
    one."""
    # Act
    outcome, grader = await _picked("It nudges its numbers whenever it gets one wrong.")

    # Assert
    assert grader.calls == 1
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.NOT_MET


async def test_an_option_authored_with_stray_whitespace_still_matches_itself() -> None:
    """``take_turn`` strips the answer before anything sees it, so the *option* has to be put on the
    same footing or it can fail to match the learner picking it. Load-bearing because options are
    model-authored: a misconception written with a trailing space is not a hypothetical."""
    # Arrange: the same card, with the option as a careless authoring call left it.
    padded = f"  {_MISCONCEPTIONS[0]}  "
    session = _quizzed()
    card = session.turns[0].surface
    assert isinstance(card, QuizCard)
    session = session.model_copy(
        update={
            "turns": [
                session.turns[0].model_copy(
                    update={"surface": card.model_copy(update={"options": [padded, _DEFINITION]})}
                )
            ]
        }
    )

    # Act: the browser sends the option's own text back.
    outcome, grader = await _took(session, padded)

    # Assert
    assert grader.calls == 0
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.NOT_MET


async def test_a_definition_authored_with_stray_whitespace_is_still_the_true_one() -> None:
    """The nastiest way this could come back. The card's true option IS the concept's definition, so
    if the definition carries whitespace the option does too, and a comparison that normalises
    neither would miss the truth, fall into the option loop, and mark the correct answer as a
    misconception. The original defect, resurrected through a space."""
    # Arrange
    padded = f"  {_DEFINITION}  "
    graph = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[_node().model_copy(update={"definition": padded})],
        topo_order=["a"],
        is_acyclic=True,
    )
    session = _quizzed()
    card = session.turns[0].surface
    assert isinstance(card, QuizCard)
    session = session.model_copy(
        update={
            "turns": [
                session.turns[0].model_copy(
                    update={
                        "surface": card.model_copy(update={"options": [*_MISCONCEPTIONS, padded]})
                    }
                )
            ]
        }
    )
    grader = _RefusingGrader()

    # Act
    outcome = await take_turn(
        session,
        graph,
        LearnerModel(graph_id="g1"),
        answer=padded,
        answering_seq=1,
        grader=grader,
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Assert
    assert grader.calls == 0
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.PARTIAL


async def test_an_option_longer_than_an_answer_may_be_still_matches_itself() -> None:
    """The other half of the same footing. ``take_turn`` truncates the answer to
    ``MAX_ANSWER_CHARS``; an option past that length would never equal what comes back from the
    learner who picked it, and would be quietly sent to the prose grader instead."""
    # Arrange: misconceptions carry no length bound of their own.
    long_option = "A wrong model, at length. " * 200
    assert len(long_option) > MAX_ANSWER_CHARS
    session = _quizzed()
    card = session.turns[0].surface
    assert isinstance(card, QuizCard)
    session = session.model_copy(
        update={
            "turns": [
                session.turns[0].model_copy(
                    update={
                        "surface": card.model_copy(update={"options": [long_option, _DEFINITION]})
                    }
                )
            ]
        }
    )

    # Act
    outcome, grader = await _took(session, long_option)

    # Assert
    assert grader.calls == 0
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.NOT_MET


async def test_the_definition_typed_when_it_was_never_on_the_card_is_prose() -> None:
    """The truth is looked for among the options, not beside them. A learner who writes the
    definition out was not recognising anything, because they were never shown it: that is a claim,
    and a claim is the grader's business."""
    # Arrange: a card offering only wrong models, which ``_quiz`` would not build but a caller can.
    session = _quizzed()
    card = session.turns[0].surface
    assert isinstance(card, QuizCard)
    session = session.model_copy(
        update={
            "turns": [
                session.turns[0].model_copy(
                    update={"surface": card.model_copy(update={"options": list(_MISCONCEPTIONS)})}
                )
            ]
        }
    )

    # Act
    _, grader = await _took(session, _DEFINITION)

    # Assert
    assert grader.calls == 1


async def test_a_card_about_another_concept_is_not_marked_against_this_one() -> None:
    """Defensive, and cheap at a surface that feeds the learner model. The card and the move name
    their concepts separately; today ``select_surface`` builds both from one node, but if they ever
    disagreed, a pick would be marked against a definition belonging to something else. Falling
    through to the grader is the safe end of that branch, not inventing a verdict."""
    # Arrange
    session = _quizzed()
    card = session.turns[0].surface
    assert isinstance(card, QuizCard)
    session = session.model_copy(
        update={
            "turns": [
                session.turns[0].model_copy(
                    update={"surface": card.model_copy(update={"node_id": "somewhere-else"})}
                )
            ]
        }
    )

    # Act
    _, grader = await _took(session, _DEFINITION)

    # Assert
    assert grader.calls == 1


# ── every other surface is untouched ─────────────────────────────────────────────────────────────


async def test_an_answer_to_a_criterion_card_is_still_graded_by_the_grader() -> None:
    """The narrow fix stays narrow: only a standing quiz card marks by recognition. A prose surface
    that happened to quote the definition back is a claim the grader still has to judge."""
    # Arrange: the same session with no card on it at all.
    session = _quizzed()
    session = session.model_copy(
        update={"turns": [session.turns[0].model_copy(update={"surface": None})]}
    )
    grader = _RefusingGrader()

    # Act
    outcome = await take_turn(
        session,
        _graph(),
        LearnerModel(graph_id="g1"),
        answer=_DEFINITION,
        answering_seq=1,
        grader=grader,
        tutor=StubTutor(),
        run_id="r2",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Assert
    assert grader.calls == 1
    graded = outcome.session.turns[0].grade
    assert graded is not None
    assert graded.kind is EvidenceKind.NOT_MET


@pytest.mark.parametrize("option", [_DEFINITION, *_MISCONCEPTIONS])
async def test_every_option_on_the_card_is_marked_without_a_model_call(option: str) -> None:
    """Table over the card's own options, so an option added to a card can never quietly reopen the
    path that sends a pick to the prose grader."""
    # Act
    _, grader = await _picked(option)

    # Assert
    assert grader.calls == 0
