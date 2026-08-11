from pydantic import Field

from ...graph.schema.base import LiveModel


class NodeKnowledge(LiveModel):
    """What the system believes about one concept, and what that belief rests on.

    ``estimate`` is the belief at the moment of its last evidence — NOT the belief now. Now is
    ``recall_of``, which decays it by how long the learner has gone without demonstrating it.
    Storing the undecayed value is what makes the row stable: a persisted number that changed
    meaning with every passing turn could not be compared with itself between sessions.

    ``evidence_count`` is deliberately kept beside the belief rather than folded into it. They
    answer different questions — the director gates on the belief, and a human auditing a session
    needs to know whether it rests on one answer or five.
    """

    node_id: str = Field(min_length=1, max_length=100)
    #: Belief at ``last_evidence_turn``, in [0, 1].
    estimate: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)
    #: The turn the last evidence arrived on — the origin decay is measured from.
    last_evidence_turn: int = Field(default=0, ge=0)
