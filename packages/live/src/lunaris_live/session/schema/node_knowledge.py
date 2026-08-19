from datetime import datetime

from pydantic import Field

from ...graph.schema.base import LiveModel
from ..review_ladder import LAST_RUNG


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
    #: What the placement interview said the learner already holds of this concept (P2c T3), in
    #: [0, 1]. A *claim*, never evidence: it does not move ``estimate`` and it does not count as
    #: demonstrated. It changes two things only — the director skips a claimed chain to its
    #: boundary and verifies the deepest claim there before building on it, and Tier 2 reads it as
    #: the band for a concept nothing has been shown about. Cleared by the first evidence.
    prior: float | None = Field(default=None, ge=0.0, le=1.0)
    #: The rung of the review ladder this concept is on (P2c T6): how many closes in a row it has
    #: held at. Zero for a concept never held at a close, and after one it slipped at.
    review_stage: int = Field(default=0, ge=0, le=LAST_RUNG)
    #: When the concept is next due for a review, set at the session's close from the rung and
    #: how the concept stood; cleared by the evidence that answers the review. ``None`` on a
    #: concept never scheduled, and on every row written before the schedule existed.
    due_at: datetime | None = None
