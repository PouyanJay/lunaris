from ..graph import ConceptGraph
from .decide_move import decide_move
from .schema import LearnerModel, MoveKind, NodeKnowledge, SessionClock


def predict_next(graph: ConceptGraph, model: LearnerModel, *, current: str) -> str | None:
    """The concept the director would move to next if the current one held: the node to prefetch.

    The director's own answer to "and if this lands?", not a second policy: the model is read as
    it would be once ``current`` is demonstrated, and ``decide_move`` says what comes next. ``None``
    when that is a close (nothing left) — and never ``current`` itself: a learner half-way through
    a concept is not about to start it, and the turn on it already has its material.

    The clock handed to the director is fresh: the prediction is about the map and the belief,
    not about the budget, which the real turn will read for itself.
    """
    held = model.nodes.get(current)
    demonstrated = NodeKnowledge(
        node_id=current,
        estimate=1.0,
        evidence_count=(held.evidence_count if held is not None else 0) + 1,
        last_evidence_turn=(held.last_evidence_turn if held is not None else 0) + 1,
    )
    as_if = model.model_copy(update={"nodes": {**model.nodes, current: demonstrated}})
    move = decide_move(
        graph,
        as_if,
        SessionClock(turn=demonstrated.last_evidence_turn + 1, elapsed_s=0.0, budget_s=1.0),
    )
    if move.kind is MoveKind.CLOSE or move.node_id is None or move.node_id == current:
        return None
    # Only a concept the learner has never been taught: a remediation or a retrieval of one with
    # evidence generates fresh material by rule (a first turn is the only turn that reads the
    # store), so prefetching for it would be spend nothing ever reads (found in review). A claim
    # with no evidence yet IS a first visit, and is kept.
    known = model.nodes.get(move.node_id)
    if known is not None and known.evidence_count > 0:
        return None
    return move.node_id
