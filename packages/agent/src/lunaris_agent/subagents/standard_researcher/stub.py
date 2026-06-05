from collections.abc import Sequence

from lunaris_runtime.schema import CourseBrief, StandardResearch

from .outcome import ResearchOutcome
from .seed_source import SeedSource


class StubStandardResearcher:
    """Returns preconfigured research findings. Lets the pipeline run without a search key.

    Defaults to ``StandardResearch()`` (``status=UNAVAILABLE``, no sources) and no seeds — the
    honest no-key outcome the composition root wires when ``SEARCH_API_KEY`` is unset, so the no-key
    CI path skips research deterministically. Tests inject grounded findings to drive the later
    stages, and optional ``seeds`` to drive the SEED feed (P6.4) without a live fetch.
    """

    def __init__(
        self,
        research: StandardResearch | None = None,
        *,
        seeds: Sequence[SeedSource] | None = None,
    ) -> None:
        self._research = research or StandardResearch()
        self._seeds: tuple[SeedSource, ...] = tuple(seeds or ())

    async def research(self, brief: CourseBrief) -> ResearchOutcome:
        return ResearchOutcome(research=self._research, seeds=self._seeds)
