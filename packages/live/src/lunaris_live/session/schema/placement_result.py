from pydantic import Field

from ...graph.schema.base import LiveModel
from .node_prior import NodePrior


class PlacementResult(LiveModel):
    """What the placement interview came to (P2c T3): who this learner is, and what they claim.

    ``profile`` is a paragraph the tutor reads on every later turn (their background, what they
    want to be able to do), or empty when the interview said nothing usable. ``priors`` are claims,
    one per node at most, seeded into the learner model as such — never as evidence.
    """

    profile: str = Field(default="", max_length=2000)
    priors: list[NodePrior] = Field(default_factory=list)
