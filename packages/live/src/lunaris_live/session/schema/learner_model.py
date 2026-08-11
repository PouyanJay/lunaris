from pydantic import Field

from ...graph.schema.base import LiveModel
from .node_knowledge import NodeKnowledge


class LearnerModel(LiveModel):
    """What the system believes one learner knows about one map.

    Keyed to a graph because node ids are graph-local — the compiler mints them per compile — so
    mastery cannot transfer between two maps of the same subject without semantic matching, which is
    not this journey's problem (R3). "Persists across sessions" (plan §11) means across sessions on
    a map, which is what this gives.

    Absent is not zero-with-a-row: a concept nobody has evidence about simply has no entry, and
    ``recall_of`` answers 0.0 for it. That keeps a fresh learner's model empty rather than a wall of
    zeroes, and it makes "how much of this map has been touched" a length rather than a scan.
    """

    graph_id: str = Field(min_length=1, max_length=100)
    #: Concept id → what is believed about it. Only concepts with evidence appear.
    nodes: dict[str, NodeKnowledge] = Field(default_factory=dict)
