from datetime import datetime

from ..graph import ConceptGraph
from .covered_in import covered_in
from .review_ladder import LAST_RUNG, review_interval
from .schema import CoveredOutcome, LearnerModel, NodeKnowledge, SessionTurn


def schedule_reviews(
    model: LearnerModel, graph: ConceptGraph, turns: list[SessionTurn], *, at: datetime
) -> LearnerModel:
    """The learner model with this session's reviews scheduled, as of ``at`` — the close (P2c T6).

    Deterministic, over what the session covered (the transcript) and how each concept stands
    (the belief): a concept that held climbs a rung and is due ``review_interval`` out; one that is
    forming is due tomorrow from the bottom of the ladder, whichever rung it was on — the ladder is
    a record of what held, not of what once held; one only introduced (nothing graded) is left to
    the frontier, not scheduled. Concepts the session never touched keep their dates.
    """
    scheduled = dict(model.nodes)
    for covered in covered_in(turns, graph, model):
        known = scheduled.get(covered.node_id)
        if known is None or covered.outcome is CoveredOutcome.INTRODUCED:
            continue
        scheduled[covered.node_id] = _rescheduled(known, covered.outcome, at=at)
    return model.model_copy(update={"nodes": scheduled})


def _rescheduled(known: NodeKnowledge, outcome: CoveredOutcome, *, at: datetime) -> NodeKnowledge:
    if outcome is CoveredOutcome.DEMONSTRATED:
        stage = min(known.review_stage + 1, LAST_RUNG)
        return known.model_copy(
            update={"review_stage": stage, "due_at": at + review_interval(stage)}
        )
    return known.model_copy(update={"review_stage": 0, "due_at": at + review_interval(1)})
