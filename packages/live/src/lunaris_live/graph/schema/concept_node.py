from pydantic import Field

from .base import LiveModel
from .node_provenance import NodeProvenance


class ConceptNode(LiveModel):
    """One atomic concept: the unit a session teaches and assesses.

    The walking skeleton carries identity and dependency only. The teaching spec (objective,
    misconceptions, depth) and the mastery criteria — the do-statements that make assessment
    generatable — land in T3, and the asset index in later phases. Fields are added here rather than
    in a parallel type so there is exactly one node contract for the whole product.
    """

    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1, max_length=2000)
    #: Ids of the concepts that must be understood before this one.
    requires: list[str] = Field(default_factory=list)
    provenance: NodeProvenance = NodeProvenance.COMPILED
