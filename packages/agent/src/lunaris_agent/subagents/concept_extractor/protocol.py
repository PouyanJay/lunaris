from typing import Protocol

from .extraction import Extraction


class IConceptExtractor(Protocol):
    """Decomposes a topic into atomic knowledge components (KCs).

    Owns ``graph.nodes`` — the smallest teachable units, each with a definition,
    difficulty estimate, and Bloom ceiling. Swappable (live model vs. test stub).
    """

    async def extract(self, topic: str) -> Extraction: ...
