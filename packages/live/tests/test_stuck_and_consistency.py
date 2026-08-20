"""When a concept will not land: lowering the bar, banking what was shown, and moving on (T8).

Two defects from the first real browser session, both about the same twenty minutes.

**The session could not move.** Six turns went by on concept one of about twenty. The tutor reframed
well — four structurally distinct analogies, which is the hard part and it works — but the criterion
was re-asked verbatim at full difficulty every single turn, so a learner who could not clear that
bar could not clear anything. `_stuck_on` reads the belief rather than a miss counter (so a
breakthrough clears it) and had no upper end at all: a concept sitting below `DECAYED` was
remediated for ever.

**The grader contradicted itself.** An answer was marked PARTIAL and told it was missing "adjusts
many small numbers (weights)"; a later answer that said exactly that was marked NOT_MET for
"restating the definition". Following the grader's own feedback cost the learner points. A grader
that is not monotonic teaches learners to ignore it, which is the one thing feedback cannot survive.

U4 is the decision behind the first fix: after repeated misses the ask shrinks (recognition rather
than production, which T1 made bankable as PARTIAL), what was shown is banked, and the session moves
on with the concept scheduled for review rather than marked mastered.
"""

from collections.abc import Sequence
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
    DirectorMove,
    EvidenceKind,
    LearnerModel,
    MoveKind,
    PriorAttempt,
    SessionClock,
    TurnGrade,
    apply_evidence,
    decide_move,
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


def _graph(*, independent: bool = True) -> ConceptGraph:
    """Two concepts. Independent by default; `independent=False` makes the second need the first."""
    return ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[_node("a", "Alpha"), _node("b", "Beta", requires=[] if independent else ["a"])],
        topo_order=["a", "b"],
        is_acyclic=True,
    )


def _clock(turn: int = 3) -> SessionClock:
    return SessionClock(turn=turn, elapsed_s=60.0, budget_s=_BUDGET_S)


def _missed(times: int, *, node: str = "a") -> LearnerModel:
    model = LearnerModel(graph_id="g1")
    for attempt in range(1, times + 1):
        model = apply_evidence(model, node, EvidenceKind.NOT_MET, at_turn=attempt)
    return model


# ── the bar comes down before the session gives up ───────────────────────────────────────────────


def test_two_misses_remediate_rather_than_pressing_on() -> None:
    """Unchanged, and asserted here so the give-up rule below cannot be read as removing it. Two
    misses is where the ask stops being "say it" and starts being "pick it out"."""
    # Act
    move = decide_move(_graph(), _missed(2), _clock())

    # Assert
    assert move.kind is MoveKind.REMEDIATE
    assert move.node_id == "a"


@pytest.mark.parametrize(
    ("evidence", "still_trying"),
    [(2, True), (3, True), (4, True), (5, False), (6, False)],
    ids=["two", "three", "four", "the-bound", "past-it"],
)
def test_where_exactly_the_session_stops_pressing_on_a_concept(
    evidence: int, still_trying: bool
) -> None:
    """The bound itself, triangulated (review finding).

    Without a case either side of it, `_GIVE_UP_AFTER` could be 3, 4, 5 or 6 and every test would
    still pass — verified by the reviewer, who reverted it to 3 and saw the suite stay green. The
    constant's own comment argues for 5 *specifically* ("a learner who takes four goes and gets
    there has done the thing this whole loop exists for"), so the number deserves a test that would
    notice it moving.
    """
    # Act
    move = decide_move(_graph(), _missed(evidence), _clock())

    # Assert
    assert (move.kind is MoveKind.REMEDIATE) is still_trying


def test_a_concept_that_will_not_land_is_eventually_left_alone() -> None:
    """The defect, as the learner met it. Without an upper end, a concept below the mastery band is
    remediated on every turn for the rest of the session, and the other nineteen are never reached.

    The learner is not marked as knowing it: they are moved on from, which is a different claim and
    the honest one. The concept keeps its evidence and goes onto the review ladder at the close.
    """
    # Act
    move = decide_move(_graph(), _missed(6), _clock())

    # Assert
    assert move.kind is not MoveKind.REMEDIATE
    assert move.node_id == "b"


def test_being_moved_on_from_is_not_being_credited() -> None:
    """The thing that would make this fix worse than the bug. A concept nobody could demonstrate
    must not end up looking demonstrated, or the map's own gating becomes a lie and dependents open
    on a concept the learner never had."""
    # Arrange
    model = _missed(6)

    # Act
    decide_move(_graph(), model, _clock())

    # Assert: the belief is untouched by the director's decision to move on.
    assert model.nodes["a"].estimate < 0.45


def test_a_session_that_ends_on_a_parked_concept_says_so() -> None:
    """The trace is read by a human deciding whether the policy is any good, and this is the one
    decision they would most want to question. "Nothing is left to introduce" would be untrue when
    something IS left and the session chose to stop pressing on it."""
    # Act: the parked concept is the only way forward, so the session has nowhere else to go.
    move = decide_move(_graph(independent=False), _missed(6), _clock())

    # Assert
    assert move.kind is MoveKind.CLOSE
    assert "another day" in move.reason.lower()
    assert "nothing on this map is left" not in move.reason.lower()


def test_a_breakthrough_still_clears_the_stuck_state() -> None:
    """The property `_stuck_on` was written for, and the one a naive attempt counter would break: a
    concept that was hard once must not be remediated for ever, and neither must it be abandoned for
    ever once the learner gets it."""
    # Arrange: missed twice, then it lands.
    model = apply_evidence(_missed(2), "a", EvidenceKind.MET, at_turn=3)
    model = apply_evidence(model, "a", EvidenceKind.MET, at_turn=4)

    # Act
    move = decide_move(_graph(), model, _clock())

    # Assert
    assert move.kind is not MoveKind.REMEDIATE


def test_a_learner_stuck_on_a_prerequisite_is_not_handed_its_dependents() -> None:
    """Moving on means moving on to something *teachable*. A concept whose prerequisite the learner
    could not demonstrate is not teachable, and handing it over would be the gating rule quietly
    suspended for exactly the learner it exists to protect."""
    # Act
    move = decide_move(_graph(independent=False), _missed(6), _clock())

    # Assert: nothing left to teach here rather than Beta on a foundation that is not there.
    assert move.kind is MoveKind.CLOSE


# ── the grader may not contradict itself ─────────────────────────────────────────────────────────


async def test_the_grader_is_shown_what_the_learner_already_tried() -> None:
    """The second defect, at its root. Each answer was graded in isolation, so nothing stopped the
    grader from asking for a mechanism, being given it, and then refusing it for being a definition.
    A grader cannot be consistent with feedback it was never shown."""
    # Arrange
    from lunaris_live.session import PriorAttempt, Session, SessionTurn, StubTutor, take_turn

    seen: list[Sequence[PriorAttempt]] = []

    class RecordingGrader:
        async def grade(
            self,
            answer: str,
            *,
            criterion: MasteryCriterion,
            node: ConceptNode,
            run_id: str,
            previously: Sequence[PriorAttempt] = (),
        ) -> TurnGrade:
            seen.append(tuple(previously))
            return TurnGrade(kind=EvidenceKind.NOT_MET, reason="Not yet.")

    graph = _graph()
    session = Session(
        session_id="s1",
        graph_id="g1",
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Opening."),
                tutor="Here is Alpha.",
                run_id="r1",
                criterion=graph.nodes[0].mastery_criteria[0],
                answer="It adjusts numbers.",
                grade=TurnGrade(kind=EvidenceKind.PARTIAL, reason="Missing the mechanism."),
            ),
            SessionTurn(
                seq=2,
                move=DirectorMove(kind=MoveKind.REMEDIATE, node_id="a", reason="Another way."),
                tutor="Try it like this.",
                run_id="r2",
                criterion=graph.nodes[0].mastery_criteria[0],
            ),
        ],
    )

    # Act
    await take_turn(
        session,
        graph,
        LearnerModel(graph_id="g1"),
        answer="It adjusts many small numbers until the output is right.",
        answering_seq=2,
        grader=RecordingGrader(),
        tutor=StubTutor(),
        run_id="r3",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Assert: the earlier attempt on this same criterion, and the verdict it was given.
    assert seen == [
        (PriorAttempt(answer="It adjusts numbers.", kind=EvidenceKind.PARTIAL),),
    ]


async def test_only_attempts_at_the_same_concept_are_carried_over() -> None:
    """A learner's answer about Beta says nothing about whether they have got Alpha. Carrying it
    over would put the grader's consistency rule to work on two unrelated things."""
    # Arrange
    from lunaris_live.session import PriorAttempt, Session, SessionTurn, StubTutor, take_turn

    seen: list[Sequence[PriorAttempt]] = []

    class RecordingGrader:
        async def grade(
            self,
            answer: str,
            *,
            criterion: MasteryCriterion,
            node: ConceptNode,
            run_id: str,
            previously: Sequence[PriorAttempt] = (),
        ) -> TurnGrade:
            seen.append(tuple(previously))
            return TurnGrade(kind=EvidenceKind.NOT_MET, reason="Not yet.")

    graph = _graph()
    session = Session(
        session_id="s1",
        graph_id="g1",
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="b", reason="Opening."),
                tutor="Here is Beta.",
                run_id="r1",
                criterion=graph.nodes[1].mastery_criteria[0],
                answer="Something about Beta.",
                grade=TurnGrade(kind=EvidenceKind.PARTIAL, reason="Half of it."),
            ),
            SessionTurn(
                seq=2,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id="a", reason="Now Alpha."),
                tutor="Here is Alpha.",
                run_id="r2",
                criterion=graph.nodes[0].mastery_criteria[0],
            ),
        ],
    )

    # Act
    await take_turn(
        session,
        graph,
        LearnerModel(graph_id="g1"),
        answer="Alpha is like this.",
        answering_seq=2,
        grader=RecordingGrader(),
        tutor=StubTutor(),
        run_id="r3",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )

    # Assert
    assert seen == [()]


async def _history_for(
    *, earlier_node: str, earlier_statement: str, asked_node: str, asked_statement: str
) -> Sequence[PriorAttempt]:
    """The history the grader is handed, for one earlier attempt and one current question.

    Parameterised over both halves of the match on purpose. A fixture that differed in the node
    *and* the criterion at once would pass whether either filter worked or neither did, which is
    exactly what the first version of these tests did (found by mutation).
    """
    from lunaris_live.session import Session, SessionTurn, StubTutor, take_turn

    seen: list[Sequence[PriorAttempt]] = []

    class RecordingGrader:
        async def grade(
            self,
            answer: str,
            *,
            criterion: MasteryCriterion,
            node: ConceptNode,
            run_id: str,
            previously: Sequence[PriorAttempt] = (),
        ) -> TurnGrade:
            seen.append(tuple(previously))
            return TurnGrade(kind=EvidenceKind.NOT_MET, reason="Not yet.")

    graph = _graph()
    session = Session(
        session_id="s1",
        graph_id="g1",
        started_at=datetime.now(UTC),
        turns=[
            SessionTurn(
                seq=1,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id=earlier_node, reason="One."),
                tutor="First.",
                run_id="r1",
                criterion=MasteryCriterion(
                    kind=MasteryCriterionKind.EXPLAIN, statement=earlier_statement
                ),
                answer="An earlier go.",
                grade=TurnGrade(kind=EvidenceKind.PARTIAL, reason="Half."),
            ),
            SessionTurn(
                seq=2,
                move=DirectorMove(kind=MoveKind.INTRODUCE, node_id=asked_node, reason="Two."),
                tutor="Second.",
                run_id="r2",
                criterion=MasteryCriterion(
                    kind=MasteryCriterionKind.EXPLAIN, statement=asked_statement
                ),
            ),
        ],
    )
    await take_turn(
        session,
        graph,
        LearnerModel(graph_id="g1"),
        answer="This one.",
        answering_seq=2,
        grader=RecordingGrader(),
        tutor=StubTutor(),
        run_id="r3",
        elapsed_s=0.0,
        budget_s=_BUDGET_S,
    )
    return seen[0]


async def test_another_bar_on_the_same_concept_is_not_carried_over() -> None:
    """A map can stage more than one bar for one concept. An attempt at "predict what happens" says
    nothing about whether they can "explain how it works", and the consistency rule applied across
    the two would have the grader owing a learner credit for answering a different question."""
    # Act
    carried = await _history_for(
        earlier_node="a",
        earlier_statement="Predict what Alpha does when the input doubles.",
        asked_node="a",
        asked_statement="Explain Alpha in your own words.",
    )

    # Assert
    assert carried == ()


async def test_the_same_bar_on_another_concept_is_not_carried_over() -> None:
    """Two concepts can be given the same wording, especially by a generated map. What a learner
    said about Beta is not evidence about Alpha, whatever the two questions happen to look like."""
    # Act
    carried = await _history_for(
        earlier_node="b",
        earlier_statement="Explain it in your own words.",
        asked_node="a",
        asked_statement="Explain it in your own words.",
    )

    # Assert
    assert carried == ()


async def test_an_earlier_go_at_this_very_bar_is_carried_over() -> None:
    """The positive case, on the same fixture, so the two refusals above cannot be passing simply
    because nothing is ever carried over."""
    # Act
    carried = await _history_for(
        earlier_node="a",
        earlier_statement="Explain it in your own words.",
        asked_node="a",
        asked_statement="Explain it in your own words.",
    )

    # Assert
    assert [attempt.answer for attempt in carried] == ["An earlier go."]


def test_the_prompt_forbids_scoring_a_fuller_answer_lower() -> None:
    """The rule itself, in the words the model is actually given. Asserted on the prompt because
    the behaviour it buys is a judgement only the keyed eval can measure — but a prompt that stopped
    carrying the rule at all would be a silent regression, and this catches that."""
    # Arrange
    from lunaris_live.session.claude_grader import _PROMPT_WITH_HISTORY

    # Assert
    assert "lower" in _PROMPT_WITH_HISTORY.lower()
    assert "{previously}" in _PROMPT_WITH_HISTORY


def test_the_remediation_reason_does_not_claim_a_miss_count_it_never_counted() -> None:
    """A wording bug from the first real session, and a small lesson about traces.

    `_stuck_on` reads the *belief*, deliberately, so that a breakthrough clears it. The reason it
    produced said "missed 2 times running", which is a different claim and was untrue of the learner
    who met it: they had got the concept once and then lost it. A trace that describes a rule the
    code does not implement is worse than one that says nothing, because it will be believed.
    """
    # Arrange: met once, then missed — two pieces of evidence, no run of misses.
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)
    model = apply_evidence(model, "a", EvidenceKind.NOT_MET, at_turn=2)

    # Act
    move = decide_move(_graph(), model, _clock())

    # Assert
    assert move.kind is MoveKind.REMEDIATE
    assert "times running" not in move.reason
