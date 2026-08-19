from collections.abc import Iterable

from .schema import LearnerModel, NodeKnowledge, NodePrior


def seed_priors(model: LearnerModel, priors: Iterable[NodePrior]) -> LearnerModel:
    """The learner model with the placement's claims on it (P2c T3).

    A claim seeds a node with nothing demonstrated: the estimate stays what evidence made it, which
    for a node never met is nothing. A node with evidence is left exactly as it is, claim discarded,
    because the grader's verdicts outrank what a learner says of themselves (U2) — a returning
    learner's second interview must not erase what they have shown. Returns a new model, as
    ``apply_evidence`` does: nothing reads a half-seeded belief.
    """
    nodes = dict(model.nodes)
    for claim in priors:
        current = nodes.get(claim.node_id)
        if current is not None and current.evidence_count > 0:
            continue
        nodes[claim.node_id] = NodeKnowledge(node_id=claim.node_id, estimate=0.0, prior=claim.prior)
    return model.model_copy(update={"nodes": nodes})
