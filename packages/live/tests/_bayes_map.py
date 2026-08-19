"""The little Bayes map three suites teach on, and the belief that has held a concept — once.

``bayes_map`` is a chain in the map's teaching order (Prior → Update → Odds by default; two nodes
when asked), one EXPLAIN criterion each, so a stub-graded answer that restates the criterion is a
MET. ``held`` is two METs on a concept (demonstrated), at a rung of the review ladder when asked.
One place because the close-ceremony, spaced-schedule and variants suites each carried a copy, and
the copies had begun to differ in what they could exercise (a two-node map, a ``held`` with no
rung), which is how a fixture goes degenerate without anyone deciding it should (P2c T9, found in
review). What each suite opens and answers with stays its own: those helpers carry the suite's
tutor, budget and clock, which are the thing under test there.
"""

from datetime import datetime

from lunaris_live.graph import ConceptGraph, ConceptNode, MasteryCriterion, MasteryCriterionKind
from lunaris_live.session import EvidenceKind, LearnerModel, apply_evidence

_NAMES = {"prior": "Prior", "update": "Update", "odds": "Odds"}
_CHAIN = ["prior", "update", "odds"]


def bayes_map(*node_ids: str) -> ConceptGraph:
    """The chain, or the first ``len(node_ids)`` of it when some are named (in chain order)."""
    ids = list(node_ids) or _CHAIN
    nodes = [
        ConceptNode(
            id=node_id,
            name=_NAMES[node_id],
            definition=f"The idea {_NAMES[node_id]}.",
            requires=[ids[index - 1]] if index else [],
            mastery_criteria=[
                MasteryCriterion(
                    kind=MasteryCriterionKind.EXPLAIN, statement=f"Explain {_NAMES[node_id]}."
                )
            ],
        )
        for index, node_id in enumerate(ids)
    ]
    return ConceptGraph(
        graph_id="g1", topic="Bayes' theorem", nodes=nodes, topo_order=ids, is_acyclic=True
    )


def held(
    model: LearnerModel, node_id: str, *, stage: int = 0, due_at: datetime | None = None
) -> LearnerModel:
    """Two METs (demonstrated), at the given rung of the ladder and due when said."""
    for turn in (1, 2):
        model = apply_evidence(model, node_id, EvidenceKind.MET, at_turn=turn)
    known = model.nodes[node_id].model_copy(update={"review_stage": stage, "due_at": due_at})
    return model.model_copy(update={"nodes": {**model.nodes, node_id: known}})
