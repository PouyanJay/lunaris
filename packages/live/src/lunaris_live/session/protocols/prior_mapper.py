from collections.abc import Sequence
from typing import Protocol

from ...graph import ConceptGraph
from ..schema import InterviewExchange, PlacementResult


class IPriorMapper(Protocol):
    """Reads a finished placement interview against the map and says where the learner is (P2c T3).

    Called once, when the map has landed and the interview has ended, with everything the learner
    said and the map's concepts. Answers with a profile the tutor reads and a claim per concept the
    learner appears to hold — claims, seeded as such (``seed_priors``), never as evidence. Nothing
    it says can skip a curriculum on its own: the director verifies a claim at the boundary before
    building on it (U2).

    ``run_id`` is the turn's own run (R5). Raises ``PriorMapperUnavailableError`` when it cannot
    place; the loop degrades that to no priors, not to a failed turn.
    """

    async def map(
        self,
        topic: str,
        exchanges: Sequence[InterviewExchange],
        graph: ConceptGraph,
        *,
        run_id: str,
    ) -> PlacementResult: ...
