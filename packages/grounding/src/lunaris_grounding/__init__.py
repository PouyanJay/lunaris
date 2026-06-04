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
from lunaris_grounding.authorities import (
    CredibilityScorer,
    ICredibilityScorer,
    InMemorySourceAuthorityStore,
    IScholarlyRegistry,
    ISourceAuthorityStore,
    ScholarlyRecord,
    ScoredSource,
    SourceAuthority,
    StubScholarlyRegistry,
    SupabaseSourceAuthorityStore,
)
from lunaris_grounding.corpus import (
    CorpusSourceSummary,
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
    YouTubeVideoSource,
    classify_domain,
    host,
)
from lunaris_grounding.embeddings import IEmbedder, StubEmbedder, VoyageEmbedder
from lunaris_grounding.evidence import Evidence, Support
from lunaris_grounding.ingest import (
    CandidateSource,
    CorpusIngestor,
    DocumentExtractor,
    ExtractedDocument,
    FolderIngestSummary,
    IDocumentExtractor,
    chunk_text,
    ingest_directory,
)
from lunaris_grounding.protocols import IEvidenceRetriever, ISupportAssessor
from lunaris_grounding.retrievers import PgVectorRetriever, StubEvidenceRetriever
from lunaris_grounding.verifier import Verifier

__all__ = [
    "CandidateSource",
    "ClaudeSupportAssessor",
    "CorpusIngestor",
    "CorpusSourceSummary",
    "CredibilityScorer",
    "DocumentExtractor",
    "Evidence",
    "ExtractedContent",
    "ExtractedDocument",
    "FolderIngestSummary",
    "GroundingDocument",
    "IContentExtractor",
    "ICorpusStore",
    "ICredibilityScorer",
    "IDocumentExtractor",
    "IEmbedder",
    "IEvidenceRetriever",
    "IScholarlyRegistry",
    "ISearchProvider",
    "ISourceAuthorityStore",
    "ISupportAssessor",
    "IVideoSource",
    "InMemoryCorpusStore",
    "InMemorySourceAuthorityStore",
    "PgVectorRetriever",
    "ResearchBudget",
    "ResourceBudget",
    "ScholarlyRecord",
    "ScoredSource",
    "SearchResult",
    "SearchVideoSource",
    "SourceAuthority",
    "StubContentExtractor",
    "StubEmbedder",
    "StubEvidenceRetriever",
    "StubScholarlyRegistry",
    "StubSearchProvider",
    "StubSupportAssessor",
    "StubVideoSource",
    "SupabaseCorpusStore",
    "SupabaseSourceAuthorityStore",
    "Support",
    "TavilySearchProvider",
    "TrafilaturaContentExtractor",
    "Verifier",
    "VideoResult",
    "VoyageEmbedder",
    "YouTubeVideoSource",
    "chunk_text",
    "classify_domain",
    "host",
    "ingest_directory",
]
