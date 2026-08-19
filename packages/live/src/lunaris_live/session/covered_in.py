from collections.abc import Sequence

from ..graph import ConceptGraph
from .is_demonstrated import is_demonstrated
from .schema import Covered, CoveredOutcome, LearnerModel, SessionTurn


def covered_in(
    turns: Sequence[SessionTurn], graph: ConceptGraph, model: LearnerModel
) -> list[Covered]:
    """What this session touched and how each concept stands, in the map's teaching order (P2c T5).

    Deterministic, from the transcript and the belief: the concepts named by the session's turns,
    each judged by the belief the grader left — demonstrated (over the bar), forming (graded, not
    there), or introduced (taught, nothing graded). The recap is briefed with this and can only
    dress it, never revise it.
    """
    touched = {turn.move.node_id for turn in turns if turn.move.node_id is not None}
    names = {node.id: node.name for node in graph.nodes}
    covered: list[Covered] = []
    for node_id in graph.topo_order:
        if node_id not in touched or node_id not in names:
            continue
        known = model.nodes.get(node_id)
        evidence = known.evidence_count if known is not None else 0
        if is_demonstrated(known):
            outcome = CoveredOutcome.DEMONSTRATED
        elif evidence > 0:
            outcome = CoveredOutcome.FORMING
        else:
            outcome = CoveredOutcome.INTRODUCED
        covered.append(
            Covered(
                node_id=node_id, concept=names[node_id], outcome=outcome, evidence_count=evidence
            )
        )
    return covered
