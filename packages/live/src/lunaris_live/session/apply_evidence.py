from datetime import datetime

from .claim_of import claim_of
from .mastery_thresholds import MASTERED
from .review_ladder import review_interval
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
    model: LearnerModel,
    node_id: str,
    kind: EvidenceKind,
    *,
    at_turn: int,
    on: datetime | None = None,
) -> LearnerModel:
    """The learner model after one graded answer about ``node_id``.

    Returns a **new** model rather than mutating: the director reads the model while the grader
    writes it, and a turn must never be able to see a half-applied belief.

    The update is an exponential move towards the evidence's target, which has the two properties
    the loop actually depends on — evidence moves the belief in its own direction, and repeated
    evidence moves it further than one piece does — without pretending to a precision nobody has
    measured yet. It is a stand-in for a fitted model, and it is one function.

    ``on`` is the wall time of the answer (P2c T6). A review answered is no longer due — or the
    director would ask it again on the very next turn — so the date moves: to the bottom of the
    ladder (tomorrow) when the day is known, a provisional date the close replaces with the real
    one; to nothing when it is not (a replay). Provisional rather than cleared, because a session
    that never closes (a crash, a tab left open) would otherwise drop the concept off the ladder for
    good; due tomorrow errs the way an unfinished session should — reviewed sooner, not lost (found
    in review). The rung is kept: it is the close's input.
    """
    current = model.nodes.get(node_id)
    estimate = _starting_from(current, kind)
    target = _TARGET[kind]

    updated = NodeKnowledge(
        node_id=node_id,
        # Clamped because floating point can leave a hair outside the range on repeated pulls, and
        # the director compares this against thresholds — a value outside [0, 1] would silently
        # disable a rule rather than fail.
        estimate=min(1.0, max(0.0, estimate + (target - estimate) * _PULL)),
        evidence_count=(current.evidence_count if current is not None else 0) + 1,
        last_evidence_turn=at_turn,
        # The first evidence settles the claim either way (P2c T3): it is not carried on.
        prior=None,
        review_stage=current.review_stage if current is not None else 0,
        due_at=on + review_interval(1) if on is not None else None,
    )
    return model.model_copy(update={"nodes": {**model.nodes, node_id: updated}})


def _starting_from(current: NodeKnowledge | None, kind: EvidenceKind) -> float:
    """Where this piece of evidence pulls from.

    Ordinarily the belief as it stands (nothing, for a concept never met). A concept the learner
    *credibly* claimed in placement — at or above the mastery bar, the same bar the director
    credits it at — and has no evidence about is the one exception (P2c T3, U2): a MET verification
    starts from the claim, so one right answer lands it demonstrated — that is what makes a claim
    worth checking rather than ignoring — while anything less starts from nothing, so a half-answer
    cannot ride a confident claim over the bar. A hesitant claim (under the bar) is a band for Tier
    2 and nothing more: its first evidence starts from nothing like any other, or a claim that
    credited no skip would still buy mastery on one answer (found in review).
    """
    if current is None:
        return 0.0
    claim = claim_of(current)
    if claim is not None and claim >= MASTERED:
        return claim if kind is EvidenceKind.MET else 0.0
    return current.estimate
