"""Lunaris grounding — evidence retrieval + the deterministic verifier (Failure-B moat).

The retriever pulls evidence for a claim; an independent assessor scores support;
deterministic code decides supported-vs-cut and enforces the publish gate (no course
ships with a live unsupported claim). Retrieval is real now (D2): candidate sources are
chunked + embedded into a Supabase pgvector corpus, and a claim is grounded by embedding
it and nearest-neighbouring that corpus. Embedder, corpus store, retriever and assessor
are all Protocols so the embedding provider, vector backend and model stay swappable, and
tests run against an in-memory cosine store with a deterministic stub embedder.
"""

from lunaris_grounding.assessors import ClaudeSupportAssessor, StubSupportAssessor
from lunaris_grounding.corpus import (
    GroundingDocument,
    ICorpusStore,
    InMemoryCorpusStore,
    SupabaseCorpusStore,
)
from lunaris_grounding.discovery import (
    ExtractedContent,
    IContentExtractor,
    ISearchProvider,
    IVideoSource,
    ResearchBudget,
    ResourceBudget,
    SearchResult,
    SearchVideoSource,
    StubContentExtractor,
    StubSearchProvider,
    StubVideoSource,
    TavilySearchProvider,
    TrafilaturaContentExtractor,
    VideoResult,
    classify_domain,
    host,
)
from lunaris_grounding.embeddings import IEmbedder, StubEmbedder, VoyageEmbedder
from lunaris_grounding.evidence import Evidence, Support
from lunaris_grounding.ingest import CandidateSource, CorpusIngestor, chunk_text
from lunaris_grounding.protocols import IEvidenceRetriever, ISupportAssessor
from lunaris_grounding.retrievers import PgVectorRetriever, StubEvidenceRetriever
from lunaris_grounding.verifier import Verifier

__all__ = [
    "CandidateSource",
    "ClaudeSupportAssessor",
    "CorpusIngestor",
    "Evidence",
    "ExtractedContent",
    "GroundingDocument",
    "IContentExtractor",
    "ICorpusStore",
    "IEmbedder",
    "IEvidenceRetriever",
    "ISearchProvider",
    "ISupportAssessor",
    "IVideoSource",
    "InMemoryCorpusStore",
    "PgVectorRetriever",
    "ResearchBudget",
    "ResourceBudget",
    "SearchResult",
    "SearchVideoSource",
    "StubContentExtractor",
    "StubEmbedder",
    "StubEvidenceRetriever",
    "StubSearchProvider",
    "StubSupportAssessor",
    "StubVideoSource",
    "SupabaseCorpusStore",
    "Support",
    "TavilySearchProvider",
    "TrafilaturaContentExtractor",
    "Verifier",
    "VideoResult",
    "VoyageEmbedder",
    "chunk_text",
    "classify_domain",
    "host",
]
