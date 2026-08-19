import re
from collections.abc import Sequence

from ..graph import ConceptGraph
from .mastery_thresholds import MASTERED
from .schema import InterviewExchange, NodePrior, PlacementResult

#: What the offline mapper claims for a concept the learner named. At the mastery bar rather than
#: above it, so it credits (the director skips it, then checks it) and reads as a claim, not a
#: certainty, in the Tier 2 band.
_NAMED = MASTERED


class StubPriorMapper:
    """A mapper that needs no model, no key and no network.

    Deterministic and legible: a concept whose name (or one of its aliases) the learner used in an
    answer is claimed at the mastery bar; one they never mentioned is not; the profile is what they
    said, joined. Enough for the offline path to place a learner past a root — a surface, and a
    review, can see the boundary being checked without a provider — and no more: reading between the
    lines is exactly the model's job.
    """

    async def map(
        self,
        topic: str,
        exchanges: Sequence[InterviewExchange],
        graph: ConceptGraph,
        *,
        run_id: str,
    ) -> PlacementResult:
        said = " ".join(exchange.answer for exchange in exchanges).lower()
        if not said.strip():
            return PlacementResult()
        priors = [
            NodePrior(node_id=node.id, prior=_NAMED)
            for node in graph.nodes
            if any(_mentions(said, name) for name in (node.name, *node.aliases))
        ]
        return PlacementResult(profile=_profile(exchanges), priors=priors)


def _mentions(said: str, name: str) -> bool:
    """Whole-word, case-insensitive: "prior" in "I know what a prior is", not in "priority"."""
    return re.search(rf"\b{re.escape(name.lower())}\b", said) is not None


def _profile(exchanges: Sequence[InterviewExchange]) -> str:
    return " ".join(exchange.answer.strip() for exchange in exchanges)[:2000]
