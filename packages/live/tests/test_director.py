"""The director: what the session does next, and why (Phase 2a, T3).

Plan §7 makes this a *policy* — "a scored rule set over knowledge-state estimates", explicitly
legible, explicitly the place pedagogical iteration will happen once real session data exists. So
it is a pure function over `(graph, learner model, clock)`: no I/O, no model call, nothing to stub.
That is what lets it be exhaustively tested without a key, and it is the only deterministic part of
the loop.

The thing under test is the *ordering of concerns*, not any one rule in isolation. A director that
introduces new material while the learner is stuck, or that never looks back at a decayed concept,
is wrong in a way no single-rule test would catch — so most of these put two rules in competition
and pin which wins.
"""

import pytest
from lunaris_live.graph import ConceptGraph, ConceptNode
from lunaris_live.session import (
    EvidenceKind,
    LearnerModel,
    MoveKind,
    SessionClock,
    apply_evidence,
    decide_move,
    recall_of,
)


def _graph() -> ConceptGraph:
    """A chain: a → b → c, plus an unrelated root d. Two independent frontiers on purpose."""
    return ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[
            ConceptNode(id="a", name="A", definition="The first idea."),
            ConceptNode(id="b", name="B", definition="Builds on A.", requires=["a"]),
            ConceptNode(id="c", name="C", definition="Builds on B.", requires=["b"]),
            ConceptNode(id="d", name="D", definition="Unrelated root."),
        ],
        topo_order=["a", "d", "b", "c"],
        is_acyclic=True,
    )


def _fresh() -> SessionClock:
    return SessionClock(turn=1, elapsed_s=0.0, budget_s=1800.0)


def _mastered(model: LearnerModel, *node_ids: str, through_turn: int = 3) -> LearnerModel:
    """Enough successful evidence that the director will treat these as met."""
    for node_id in node_ids:
        for turn in range(1, through_turn + 1):
            model = apply_evidence(model, node_id, EvidenceKind.MET, at_turn=turn)
    return model


# ── introducing ───────────────────────────────────────────────────────────────────────────────


def test_a_fresh_session_introduces_a_concept_with_no_prerequisites() -> None:
    # Act
    move = decide_move(_graph(), LearnerModel(graph_id="g1"), _fresh())

    # Assert
    assert move.kind is MoveKind.INTRODUCE
    assert move.node_id in {"a", "d"}
    assert move.reason


def test_a_concept_whose_prerequisites_are_unmet_is_never_introduced() -> None:
    """The whole reason Phase 1 built prerequisite edges. Teaching C to somebody who has not met B
    is the failure the graph exists to prevent, and it is the director that has to honour it."""
    # Arrange — nothing known at all.
    model = LearnerModel(graph_id="g1")

    # Act
    move = decide_move(_graph(), model, _fresh())

    # Assert
    assert move.node_id not in {"b", "c"}


def test_mastering_a_prerequisite_unlocks_what_it_gates() -> None:
    """The load-bearing claim of the whole policy: progress through the map is *earned*, and the
    learner model is what earns it."""
    # Arrange
    model = _mastered(LearnerModel(graph_id="g1"), "a", "d")

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=4, elapsed_s=60.0, budget_s=1800.0))

    # Assert
    assert move.kind is MoveKind.INTRODUCE
    assert move.node_id == "b"


def test_one_right_answer_does_not_unlock_the_next_concept() -> None:
    """One right answer can be a guess. If a single MET unlocked a dependent, the map would be a
    railway with an extra step, and the learner model would be decoration."""
    # Arrange
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=2, elapsed_s=30.0, budget_s=1800.0))

    # Assert — still INTRODUCING "a", not moving on and not congratulating itself by switching to
    # review. Both halves are load-bearing: asserting merely "not b" passes when a lowered mastery
    # threshold picks the other root instead, and asserting only the node id passes when the same
    # threshold turns the move into a retrieval of a concept taught once.
    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "a")


def test_the_trace_does_not_call_a_second_pass_a_first_one() -> None:
    """The reason is the audit trail (plan §7), and the part nobody can check against anything
    else. A director reporting "the next thing this map can teach" while going back over a concept
    the learner has already met would be lying in the only record of its own judgement."""
    # Arrange — one right answer: not enough for mastery, so the session stays on "a".
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.MET, at_turn=1)

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=2, elapsed_s=30.0, budget_s=1800.0))

    # Assert
    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "a")
    assert "next thing this map can teach" not in move.reason
    assert "not yet shown" in move.reason


# ── remediating ───────────────────────────────────────────────────────────────────────────────


def test_a_learner_who_keeps_failing_is_remediated_not_advanced() -> None:
    """The competition that matters most. There is other material available and the clock is fine —
    the director must still not walk away from somebody who is stuck."""
    # Arrange — repeated failure on an available root.
    model = LearnerModel(graph_id="g1")
    for turn in (1, 2):
        model = apply_evidence(model, "a", EvidenceKind.NOT_MET, at_turn=turn)

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=3, elapsed_s=90.0, budget_s=1800.0))

    # Assert
    assert move.kind is MoveKind.REMEDIATE
    assert move.node_id == "a"


def test_one_wrong_answer_is_not_yet_being_stuck() -> None:
    """Remediating on the first miss would make the session flinch. A learner is allowed to be
    wrong once — that is what the first attempt is for."""
    # Arrange
    model = apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.NOT_MET, at_turn=1)

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=2, elapsed_s=30.0, budget_s=1800.0))

    # Assert
    assert move.kind is not MoveKind.REMEDIATE


def test_progress_after_a_struggle_stops_the_remediation() -> None:
    """Otherwise a concept that was hard once is remediated forever, and the session never moves."""
    # Arrange — stuck, then a breakthrough.
    model = LearnerModel(graph_id="g1")
    for turn in (1, 2):
        model = apply_evidence(model, "a", EvidenceKind.NOT_MET, at_turn=turn)
    for turn in (3, 4, 5):
        model = apply_evidence(model, "a", EvidenceKind.MET, at_turn=turn)

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=6, elapsed_s=200.0, budget_s=1800.0))

    # Assert
    assert move.kind is not MoveKind.REMEDIATE


# ── retrieving ────────────────────────────────────────────────────────────────────────────────


def test_a_decayed_concept_is_retrieved_before_new_material_is_introduced() -> None:
    """Spaced retrieval only exists if it can *interrupt*. A director that introduced whenever
    anything was introducible would never come back to anything."""
    # Arrange — "a" mastered long ago, "d" never seen, so both a retrieval and an introduction are
    # available and the director has to choose.
    model = _mastered(LearnerModel(graph_id="g1"), "a")

    # Act — far enough past that evidence for recall to have decayed.
    move = decide_move(_graph(), model, SessionClock(turn=40, elapsed_s=900.0, budget_s=1800.0))

    # Assert
    assert move.kind is MoveKind.RETRIEVE
    assert move.node_id == "a"


def test_a_freshly_demonstrated_concept_is_not_retrieved() -> None:
    """Retrieval immediately after the answer that established it is not spacing, it is nagging."""
    # Arrange
    model = _mastered(LearnerModel(graph_id="g1"), "a")

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=4, elapsed_s=90.0, budget_s=1800.0))

    # Assert
    assert move.kind is not MoveKind.RETRIEVE


def test_a_concept_already_demonstrated_is_never_introduced_again() -> None:
    """Found by running a whole session rather than by reading the rules (T5).

    Recall slips under ``_MASTERED`` long before it falls under ``_DECAYED``, and a concept sitting
    in that band used to be neither known (so the frontier offered it) nor faded enough to retrieve
    — so the director taught it again from the beginning, to a learner who had just proved it. The
    fix is that what was *earned* is judged on the undecayed belief; only what has *faded* is judged
    on recall.
    """
    # Arrange — "a" mastered, then far enough on that its recall has slipped below the mastery bar
    # but not yet far enough to be due for retrieval.
    model = _mastered(LearnerModel(graph_id="g1"), "a")
    clock = SessionClock(turn=14, elapsed_s=300.0, budget_s=1800.0)
    assert 0.45 <= recall_of(model, "a", at_turn=clock.turn) < 0.6, "the band this test is about"

    # Act
    move = decide_move(_graph(), model, clock)

    # Assert — on to the untouched root instead.
    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "d")


def test_a_faded_prerequisite_does_not_lock_a_learner_out_of_what_they_earned() -> None:
    """The other half: an unlock is earned once. If a prerequisite's *decayed* recall gated the
    frontier, a learner would lose access to material they had already opened simply by spending
    turns elsewhere — and with nothing introducible left, the session would close early."""
    # Arrange — "a" and "d" mastered long enough ago that recall has slipped below the bar.
    model = _mastered(LearnerModel(graph_id="g1"), "a", "d")
    clock = SessionClock(turn=14, elapsed_s=300.0, budget_s=1800.0)

    # Act
    move = decide_move(_graph(), model, clock)

    # Assert
    assert (move.kind, move.node_id) == (MoveKind.INTRODUCE, "b")


def test_a_concept_never_demonstrated_is_introduced_rather_than_retrieved() -> None:
    """Recall of an unseen concept is 0.0, which is below any decay threshold — so a naive rule
    would "retrieve" something the learner has never been taught."""
    # Act
    move = decide_move(_graph(), LearnerModel(graph_id="g1"), _fresh())

    # Assert
    assert move.kind is MoveKind.INTRODUCE


# ── closing ───────────────────────────────────────────────────────────────────────────────────


def test_the_session_closes_when_its_clock_is_spent() -> None:
    """Bounded by design (plan §6): a session that could run forever has no shape a learner can
    feel and no cost ceiling."""
    # Act — plenty left to teach, but the time is gone.
    move = decide_move(
        _graph(),
        LearnerModel(graph_id="g1"),
        SessionClock(turn=60, elapsed_s=1800.0, budget_s=1800.0),
    )

    # Assert
    assert move.kind is MoveKind.CLOSE
    assert move.node_id is None


def test_the_session_closes_when_the_map_is_exhausted() -> None:
    """Nothing left worth doing is a reason to stop, not a reason to loop."""
    # Arrange — everything mastered, and recently, so no retrieval is due either.
    model = _mastered(LearnerModel(graph_id="g1"), "a", "b", "c", "d")

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=4, elapsed_s=300.0, budget_s=1800.0))

    # Assert
    assert move.kind is MoveKind.CLOSE


def test_a_spent_clock_closes_even_on_a_learner_who_is_stuck() -> None:
    """The clock outranks everything. Remediation is the strongest pull in the policy, and it still
    must not run a session past its budget."""
    # Arrange
    model = LearnerModel(graph_id="g1")
    for turn in (1, 2, 3):
        model = apply_evidence(model, "a", EvidenceKind.NOT_MET, at_turn=turn)

    # Act
    move = decide_move(_graph(), model, SessionClock(turn=4, elapsed_s=2000.0, budget_s=1800.0))

    # Assert
    assert move.kind is MoveKind.CLOSE


def test_an_empty_map_closes_rather_than_failing() -> None:
    """A director asked to teach nothing should end the session, not raise into the loop."""
    # Arrange
    empty = ConceptGraph(graph_id="g1", topic="t", topo_order=[], is_acyclic=True)

    # Act / Assert
    assert decide_move(empty, LearnerModel(graph_id="g1"), _fresh()).kind is MoveKind.CLOSE


# ── the trace ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("model_builder", "clock"),
    [
        pytest.param(lambda: LearnerModel(graph_id="g1"), _fresh(), id="introduce"),
        pytest.param(
            lambda: _mastered(LearnerModel(graph_id="g1"), "a"),
            SessionClock(turn=40, elapsed_s=900.0, budget_s=1800.0),
            id="retrieve",
        ),
        pytest.param(
            lambda: apply_evidence(
                apply_evidence(LearnerModel(graph_id="g1"), "a", EvidenceKind.NOT_MET, at_turn=1),
                "a",
                EvidenceKind.NOT_MET,
                at_turn=2,
            ),
            SessionClock(turn=3, elapsed_s=90.0, budget_s=1800.0),
            id="remediate",
        ),
        pytest.param(
            lambda: LearnerModel(graph_id="g1"),
            SessionClock(turn=60, elapsed_s=1800.0, budget_s=1800.0),
            id="close",
        ),
    ],
)
def test_every_move_says_why_in_words_a_person_can_read(
    model_builder: object, clock: SessionClock
) -> None:
    """Plan §7: "the director emits its reasoning into the session trace so every move is
    auditable". A session is dozens of choices made in seconds on a learner's behalf, and this is
    the only way to tell a good policy from a lucky one afterwards.

    Asserted on every branch, because the branch that forgets is always the one nobody exercised.
    """
    # Act
    move = decide_move(_graph(), model_builder(), clock)  # type: ignore[operator]

    # Assert — prose, not a rule id: the reason is read by a human, not parsed.
    assert len(move.reason) > 20
    assert move.reason[0].isupper()


def test_the_reason_names_the_concept_the_move_is_about() -> None:
    """A trace that said "introducing a new concept" without saying which is not auditable — it
    describes the policy rather than the decision."""
    # Act
    move = decide_move(_graph(), _mastered(LearnerModel(graph_id="g1"), "a", "d"), _fresh())

    # Assert
    assert move.node_id == "b"
    assert "B" in move.reason or "b" in move.reason


def test_the_director_never_invents_a_concept_that_is_not_on_the_map() -> None:
    """The one structural guarantee the loop above it relies on: whatever the policy decides, the
    tutor has to be able to look the concept up."""
    # Arrange
    graph = _graph()
    ids = {node.id for node in graph.nodes}

    # Act / Assert — across a spread of states, the answer is always on the map or is a close.
    model = LearnerModel(graph_id="g1")
    for turn in range(1, 25):
        move = decide_move(
            graph, model, SessionClock(turn=turn, elapsed_s=turn * 30.0, budget_s=1800.0)
        )
        assert move.node_id is None or move.node_id in ids
        if move.node_id is not None:
            model = apply_evidence(model, move.node_id, EvidenceKind.MET, at_turn=turn)


def test_a_lying_teaching_order_cannot_smuggle_a_concept_past_its_prerequisites() -> None:
    """The director does not own the order it is handed.

    Against a *valid* ``topo_order`` the prerequisite check is redundant — the first unknown concept
    in teaching order has all its prerequisites behind it, and they were only skipped because they
    were known. So the check is only observable against an order that lies, which is exactly the
    case it exists for: C1 grows maps at runtime, and these are public functions anyone can call
    with a hand-built graph. Without this test the guard is invisible and the next refactor deletes
    it as dead code.
    """
    # Arrange — an order that puts C first, though C needs B which needs A. Nothing is known.
    lying = ConceptGraph(
        graph_id="g1",
        topic="A subject",
        nodes=[
            ConceptNode(id="a", name="A", definition="The first idea."),
            ConceptNode(id="b", name="B", definition="Builds on A.", requires=["a"]),
            ConceptNode(id="c", name="C", definition="Builds on B.", requires=["b"]),
        ],
        topo_order=["c", "b", "a"],
        is_acyclic=True,
    )

    # Act
    move = decide_move(lying, LearnerModel(graph_id="g1"), _fresh())

    # Assert — it teaches the only concept that is actually reachable, not the one listed first.
    assert move.kind is MoveKind.INTRODUCE
    assert move.node_id == "a"
