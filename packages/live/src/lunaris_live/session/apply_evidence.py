from .schema import EvidenceKind, LearnerModel, NodeKnowledge

#: Where one piece of evidence pulls the belief. MET pulls towards certainty, NOT_MET towards
#: ignorance, PARTIAL towards a middle that is genuinely "nearly" rather than a shrug.
_TARGET: dict[EvidenceKind, float] = {
    EvidenceKind.MET: 1.0,
    EvidenceKind.PARTIAL: 0.5,
    EvidenceKind.NOT_MET: 0.0,
}

#: How far the belief travels towards that target on a single piece of evidence.
#:
#: Deliberately well under 1: one right answer can be a guess, and the whole reason the director can
#: gate an introduction on "its prerequisites are mastered" is that mastery takes more than one. The
#: value is provisional — there is no session data to fit it to yet, and this is the dial the
#: simulated-learner eval (T9) exists to put pressure on.
_PULL = 0.45


def apply_evidence(
    model: LearnerModel, node_id: str, kind: EvidenceKind, *, at_turn: int
) -> LearnerModel:
    """The learner model after one graded answer about ``node_id``.

    Returns a **new** model rather than mutating: the director reads the model while the grader
    writes it, and a turn must never be able to see a half-applied belief.

    The update is an exponential move towards the evidence's target, which has the two properties
    the loop actually depends on — evidence moves the belief in its own direction, and repeated
    evidence moves it further than one piece does — without pretending to a precision nobody has
    measured yet. It is a stand-in for a fitted model, and it is one function.
    """
    current = model.nodes.get(node_id)
    estimate = current.estimate if current is not None else 0.0
    target = _TARGET[kind]

    updated = NodeKnowledge(
        node_id=node_id,
        # Clamped because floating point can leave a hair outside the range on repeated pulls, and
        # the director compares this against thresholds — a value outside [0, 1] would silently
        # disable a rule rather than fail.
        estimate=min(1.0, max(0.0, estimate + (target - estimate) * _PULL)),
        evidence_count=(current.evidence_count if current is not None else 0) + 1,
        last_evidence_turn=at_turn,
    )
    return model.model_copy(update={"nodes": {**model.nodes, node_id: updated}})
