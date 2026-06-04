"""The no-op discoverer — the no-key / offline default."""

from ..draft import CourseDraft
from .report import DiscoveryReport


class StubGroundingDiscoverer:
    """Ingests nothing and reports an empty pass (the no-search-key default).

    Lets the agent pipeline run end-to-end offline: the ``discover_grounding`` tool still lights the
    Grounding phase, but no source is fetched, so claims fall to the verifier's existing behaviour
    (CUT against an empty corpus → REVIEW). The live :class:`SubgraphGroundingDiscoverer` replaces
    it when the search + corpus credentials are present.
    """

    async def discover(self, draft: CourseDraft) -> DiscoveryReport:
        return DiscoveryReport()
