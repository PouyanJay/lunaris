"""The live grounding discoverer: finds, vets, and ingests evidence for a course's concepts (P6.3).

Runs the bounded LangGraph discovery sub-graph (plan → search → fetch → gate → ingest) behind the
``discover_grounding`` tool, then reports what landed. The sub-graph grades every machine-found
source with the credibility scorer and drops off-topic ones with a label-blind judge, so the corpus
the verifier retrieves from is filled trustworthily, not just filled.
"""

from collections.abc import Callable

import structlog
from lunaris_grounding import CorpusIngestor, IContentExtractor, ICredibilityScorer, ISearchProvider

from ..draft import CourseDraft
from .budget import DiscoveryBudget
from .loop import build_discovery_subgraph
from .relevance_judge import IRelevanceJudge
from .report import DiscoveryReport

logger = structlog.get_logger()


class SubgraphGroundingDiscoverer:
    """Discovers + ingests grounding evidence for a course by running the discovery sub-graph.

    Holds the discovery collaborators — the search provider, content extractor, credibility scorer
    (the seam where machine-found sources are graded), the label-blind relevance judge, and the
    corpus ingestor (a Voyage embedder + the pgvector store in production, an in-memory store + stub
    embedder in tests). ``clock`` stamps ``fetched_at`` and is injectable so the offline suite is
    deterministic.
    """

    def __init__(
        self,
        search: ISearchProvider,
        extractor: IContentExtractor,
        scorer: ICredibilityScorer,
        judge: IRelevanceJudge,
        ingestor: CorpusIngestor,
        *,
        budget: DiscoveryBudget | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._search = search
        self._extractor = extractor
        self._scorer = scorer
        self._judge = judge
        self._ingestor = ingestor
        self._budget = budget
        self._clock = clock

    async def discover(self, draft: CourseDraft) -> DiscoveryReport:
        # Pass budget/clock through only when set; the sub-graph owns the default budget + clock.
        overrides: dict[str, object] = {}
        if self._budget is not None:
            overrides["budget"] = self._budget
        if self._clock is not None:
            overrides["clock"] = self._clock
        graph = build_discovery_subgraph(
            self._search,
            self._extractor,
            self._scorer,
            self._judge,
            self._ingestor,
            draft,
            **overrides,
        )
        state = await graph.ainvoke({})
        accepted = state.get("accepted", [])
        report = DiscoveryReport(
            chunks_ingested=state.get("chunks_ingested", 0),
            sources_accepted=len(accepted),
            covered_kcs=tuple(state.get("covered_kcs", [])),
        )
        logger.info(
            "grounding_discovered",
            run_id=draft.run_id,
            course_id=draft.course_id,
            chunks=report.chunks_ingested,
            sources=report.sources_accepted,
            covered=len(report.covered_kcs),
        )
        return report
