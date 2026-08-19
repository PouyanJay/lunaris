from .claim_of import claim_of
from .schema import LearnerModel


def opening_beliefs_of(model: LearnerModel) -> dict[str, float]:
    """What a session opens believing about each concept: the mastery delta's zero line (P2c T5).

    The undecayed estimate for a concept with evidence (recall at open equals it: decay is measured
    in turns of this session, and none have passed), and the claim for a concept the interview
    placed but nothing has checked — the learner said they held it, and the meter should say "you
    came in claiming this" rather than "you started from nothing". Concepts with neither are absent.
    """
    beliefs: dict[str, float] = {}
    for node_id, known in model.nodes.items():
        if known.evidence_count > 0:
            beliefs[node_id] = known.estimate
        elif (claim := claim_of(known)) is not None:
            beliefs[node_id] = claim
    return beliefs
