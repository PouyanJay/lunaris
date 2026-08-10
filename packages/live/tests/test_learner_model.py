"""What the system believes the learner knows, and how that belief moves (Phase 2a, T2).

This is the half of the loop the director reads and the grader writes. It is deliberately a small
pure domain — no I/O, no model call — because it is the one part of a session that must be
inspectable after the fact: "why did it teach me that" is answered by the graph plus this.

Two properties matter more than the exact numbers, and the numbers are explicitly provisional
(there is no session data to fit a curve to yet):

- **evidence moves the belief in the direction of the evidence**, and repeated evidence moves it
  further than one piece of it; and
- **belief decays without evidence**, or spaced retrieval has nothing to be spaced against.
"""

import pytest
from lunaris_live.session import (
    EvidenceKind,
    LearnerModel,
    NodeKnowledge,
    apply_evidence,
    recall_of,
)


def _model() -> LearnerModel:
    return LearnerModel(graph_id="g1")


# ── what evidence does ────────────────────────────────────────────────────────────────────────


def test_a_concept_nobody_has_evidence_about_is_not_assumed_known() -> None:
    """The opening state of every node. Assuming knowledge would have the director skip concepts
    the learner has never seen; assuming ignorance is the safe direction to be wrong in."""
    assert recall_of(_model(), "never-seen", at_turn=1) == 0.0


def test_meeting_a_criterion_raises_the_belief() -> None:
    # Arrange / Act
    model = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Assert
    assert recall_of(model, "a", at_turn=1) > 0.0


def test_failing_a_criterion_lowers_a_belief_that_was_high() -> None:
    """The direction that matters most: a learner who has drifted must be *findable*, or the
    director will keep introducing new material on a foundation that has gone."""
    # Arrange — a well-established concept.
    model = _model()
    for turn in range(1, 4):
        model = apply_evidence(model, "a", EvidenceKind.MET, at_turn=turn)
    established = recall_of(model, "a", at_turn=3)

    # Act
    model = apply_evidence(model, "a", EvidenceKind.NOT_MET, at_turn=4)

    # Assert
    assert recall_of(model, "a", at_turn=4) < established


def test_repeated_success_believes_more_than_a_single_success() -> None:
    """One right answer can be a guess. This is what makes "mastered" mean something the director
    can gate an introduction on."""
    # Arrange
    once = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Act
    thrice = once
    for turn in (2, 3):
        thrice = apply_evidence(thrice, "a", EvidenceKind.MET, at_turn=turn)

    # Assert
    assert recall_of(thrice, "a", at_turn=3) > recall_of(once, "a", at_turn=3)


def test_a_partial_answer_counts_for_less_than_a_full_one() -> None:
    """The grader's middle verdict has to mean something, or it collapses into one of its
    neighbours and the tutor loses the ability to say "nearly"."""
    partial = apply_evidence(_model(), "a", EvidenceKind.PARTIAL, at_turn=1)
    met = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    assert 0.0 < recall_of(partial, "a", at_turn=1) < recall_of(met, "a", at_turn=1)


def test_evidence_about_one_concept_moves_only_that_concept() -> None:
    """The bug that would make the whole model meaningless: mastery has to be per concept, or the
    director's "are its prerequisites met" question has no answer."""
    # Arrange
    model = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Act / Assert
    assert recall_of(model, "b", at_turn=1) == 0.0


def test_the_model_records_how_much_evidence_it_has_seen() -> None:
    """A belief and the evidence behind it are different things. The director gates on the belief;
    a human auditing a session needs to know whether it rests on one answer or five."""
    # Arrange / Act
    model = _model()
    for turn in (1, 2):
        model = apply_evidence(model, "a", EvidenceKind.MET, at_turn=turn)

    # Assert
    assert model.nodes["a"].evidence_count == 2
    assert model.nodes["a"].last_evidence_turn == 2


def test_applying_evidence_does_not_mutate_the_model_it_was_given() -> None:
    """The director reads the model while the grader writes it. Returning a new one means a turn
    can never see a half-applied belief."""
    # Arrange
    before = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Act
    after = apply_evidence(before, "a", EvidenceKind.NOT_MET, at_turn=2)

    # Assert
    assert recall_of(before, "a", at_turn=1) != recall_of(after, "a", at_turn=2)
    assert before.nodes["a"].evidence_count == 1


# ── what time does ────────────────────────────────────────────────────────────────────────────


def test_belief_decays_when_nothing_reinforces_it() -> None:
    """Without this, spaced retrieval has nothing to be spaced against — every concept would stay
    at the value its last answer left it at, forever, and the director would never look back."""
    # Arrange
    model = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Act / Assert
    assert recall_of(model, "a", at_turn=30) < recall_of(model, "a", at_turn=1)


def test_decay_never_reaches_certainty_that_the_learner_forgot() -> None:
    """A concept demonstrated once is not the same as one never seen: the director should prefer
    retrieving the first over introducing it from scratch, so it must not decay to zero."""
    # Arrange
    model = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Act / Assert — far past any real session length.
    assert recall_of(model, "a", at_turn=10_000) > 0.0


def test_stronger_beliefs_survive_longer() -> None:
    """The point of repetition. Two concepts left alone for the same span must not be equally
    forgotten if one was better established."""
    # Arrange
    weak = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)
    strong = weak
    for turn in (2, 3, 4):
        strong = apply_evidence(strong, "a", EvidenceKind.MET, at_turn=turn)

    # Act / Assert — measured at the same distance from each one's last evidence.
    assert recall_of(strong, "a", at_turn=24) > recall_of(weak, "a", at_turn=21)


def test_recall_is_asked_of_a_turn_and_never_of_a_clock() -> None:
    """Decay is measured in turns, not wall time, so a session is reproducible: replaying the same
    answers gives the same beliefs, which is what makes the simulated-learner eval (T9) mean
    anything. Cross-session forgetting is real and is NOT this — an open question, not modelled."""
    # Arrange
    model = apply_evidence(_model(), "a", EvidenceKind.MET, at_turn=1)

    # Act / Assert — the same turn always gives the same answer, however long the test takes.
    assert recall_of(model, "a", at_turn=9) == recall_of(model, "a", at_turn=9)


@pytest.mark.parametrize("kind", list(EvidenceKind))
def test_a_belief_is_always_a_probability(kind: EvidenceKind) -> None:
    """Whatever the evidence, the number stays in [0, 1] — the director compares it against
    thresholds, and a value outside the range would silently disable a rule."""
    # Arrange
    model = _model()

    # Act — far more evidence than any real session produces.
    for turn in range(1, 40):
        model = apply_evidence(model, "a", kind, at_turn=turn)

    # Assert
    assert 0.0 <= recall_of(model, "a", at_turn=40) <= 1.0
    assert 0.0 <= model.nodes["a"].estimate <= 1.0


def test_a_knowledge_row_can_be_rebuilt_from_its_wire_shape() -> None:
    """The model is persisted per node and read back on the next session (R3), so its round trip is
    part of the contract rather than an implementation detail."""
    # Arrange
    original = NodeKnowledge(node_id="a", estimate=0.62, evidence_count=3, last_evidence_turn=7)

    # Act
    restored = NodeKnowledge.model_validate(original.model_dump(mode="json", by_alias=True))

    # Assert
    assert restored == original
