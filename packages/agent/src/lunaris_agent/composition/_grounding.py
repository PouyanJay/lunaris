import os

import structlog
from lunaris_grounding import (
    CorpusIngestor,
    CredibilityScorer,
    DuckDuckGoSearchProvider,
    IEmbedder,
    IEvidenceRetriever,
    ISearchProvider,
    LocalEmbedder,
    OpenAlexScholarlyRegistry,
    PgVectorRetriever,
    SupabaseCorpusStore,
    SupabaseSourceAuthorityStore,
    TavilySearchProvider,
    TrafilaturaContentExtractor,
    VoyageEmbedder,
)
from lunaris_runtime.credentials import resolve_secret

from ..harness.discovery import (
    ClaudeRelevanceJudge,
    IGroundingDiscoverer,
    StubGroundingDiscoverer,
    SubgraphGroundingDiscoverer,
)
from ..harness.seeding import GroundingSeeder, IGroundingSeeder, StubGroundingSeeder

logger = structlog.get_logger()


def _embedder_from_env() -> IEmbedder:
    """The embedder for a run: Voyage when its key is set, else the keyless local fallback (nano).

    Embeddings are no longer key-gated: with no key the run uses the local nano fallback (over an
    OpenAI-compatible endpoint), so grounding still works keyless. Nano and Voyage are different
    vector spaces, so a corpus ingests + queries under one embedder; a switch means re-grounding.
    """
    if resolve_secret("EMBEDDINGS_API_KEY"):
        return VoyageEmbedder()
    logger.info("embedder_local_fallback", reason="EMBEDDINGS_API_KEY unset")
    return LocalEmbedder()


def _retriever_from_env() -> IEvidenceRetriever | None:
    """Build the real pgvector retriever iff the Supabase corpus is present.

    Embeddings are keyless (Voyage when keyed, else the local nano fallback), so this gates only on
    the Supabase corpus store. Returns ``None`` (→ the verifier falls back to the conservative stub
    that cuts every claim) only when Supabase is unset, so the pipeline still runs corpus-less.
    """
    if _has_supabase_corpus():
        return PgVectorRetriever(_embedder_from_env(), SupabaseCorpusStore())
    logger.info("grounding_retriever_stubbed", reason="supabase corpus unset")
    return None


def _search_provider_from_env() -> ISearchProvider:
    """The web-search provider for a run: Tavily when its key is set, else keyless DuckDuckGo.

    Search is no longer key-gated — with no ``SEARCH_API_KEY`` the run searches via DuckDuckGo (no
    key), so research / discovery / resource curation still run keyless instead of stubbing out.
    """
    if resolve_secret("SEARCH_API_KEY"):
        return TavilySearchProvider()
    logger.info("search_provider_duckduckgo_fallback", reason="SEARCH_API_KEY unset")
    return DuckDuckGoSearchProvider()


def _discoverer_from_env(worker_model: str) -> IGroundingDiscoverer:
    """Build the live grounding discoverer iff the Supabase corpus is present (P6.3).

    Search + embeddings are keyless (DuckDuckGo / local nano when their keys are unset), so it
    gates only on the Supabase corpus (the store the verifier retrieves from). Without it the stub
    is returned (no source ingested), so the corpus-less path stays deterministic and claims fall
    to REVIEW. The discovery sub-graph grades each source with the credibility scorer — backed by
    the seeded authorities table + the live OpenAlex registry (keyless; optional ``OPENALEX_EMAIL``
    for its polite pool), which floors an unknown host serving a real paper to REPUTABLE — and drops
    off-topic ones with a label-blind worker-tier judge, so machine-found evidence is graded, not
    just gathered.
    """
    if _has_supabase_corpus():
        return SubgraphGroundingDiscoverer(
            _search_provider_from_env(),
            TrafilaturaContentExtractor(),
            _credibility_scorer(),
            ClaudeRelevanceJudge(worker_model),
            CorpusIngestor(_embedder_from_env(), SupabaseCorpusStore()),
        )
    logger.info("grounding_discoverer_stubbed", reason="supabase corpus unset")
    return StubGroundingDiscoverer()


def _seeder_from_env() -> IGroundingSeeder:
    """Build the live grounding seeder iff the Supabase corpus is present (P6.4).

    Embeddings are keyless (local nano when no Voyage key), so seeding gates only on the Supabase
    corpus (to ingest into the same store the verifier retrieves from); it needs no search key,
    since it reuses pages the research stage already fetched. Its ingestor carries the credibility
    scorer (backed by the seeded authorities table + the live OpenAlex registry), so each seed is
    graded through the SAME gate as an auto-discovered source: seeded is not the same as trusted.
    Without the corpus it returns the stub (nothing ingested), so the corpus-less path stays
    deterministic and claims fall to the verifier's existing behaviour.
    """
    if _has_supabase_corpus():
        ingestor = CorpusIngestor(
            _embedder_from_env(), SupabaseCorpusStore(), scorer=_credibility_scorer()
        )
        return GroundingSeeder(ingestor)
    logger.info("grounding_seeder_stubbed", reason="supabase corpus unset")
    return StubGroundingSeeder()


def _has_supabase_corpus() -> bool:
    """Whether the Supabase corpus (the store the verifier retrieves from) is configured."""
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))


def _credibility_scorer() -> CredibilityScorer:
    """The shared source-grading gate: seeded authorities table + the live OpenAlex registry."""
    return CredibilityScorer(
        SupabaseSourceAuthorityStore(),
        registry=OpenAlexScholarlyRegistry(mailto=os.getenv("OPENALEX_EMAIL")),
    )
