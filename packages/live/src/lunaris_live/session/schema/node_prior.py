from pydantic import Field

from ...graph.schema.base import LiveModel


class NodePrior(LiveModel):
    """One claim from the placement interview: how much of ``node_id`` the learner says they hold.

    Sibling of ``PlacementResult``, which carries a list of these; kept apart so the store and the
    seeding function speak of a claim without the profile beside it.
    """

    node_id: str = Field(min_length=1, max_length=100)
    prior: float = Field(ge=0.0, le=1.0)
