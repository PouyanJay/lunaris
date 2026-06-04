from dataclasses import dataclass

from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier


@dataclass(frozen=True)
class CandidateSource:
    """A candidate grounding source for a KC, before chunking/embedding.

    D3 (MVP): general/open retrieval feeds these in; ingestion chunks ``text``, embeds it,
    and writes the chunks to the corpus keyed by ``kc_id``.

    The trust/provenance fields (P6.0) are constructed where the source is acquired (manual upload,
    auto-discovery, or a build-time seed) and flow untouched through ingestion onto the corpus chunk
    and the citation, so a claim's evidence is graded and auditable. All optional — a source with no
    classification ingests as un-tiered. ``course_id`` scopes the chunk to one course; retrieval
    filters on it, so no other topic's evidence can bleed in.
    """

    kc_id: str
    text: str
    title: str | None = None
    url: str | None = None
    source_type: SourceType | None = None
    trust_tier: TrustTier | None = None
    credibility: float | None = None
    fetched_at: str | None = None  # ISO-8601 instant, stamped at acquisition
    acquisition_mode: AcquisitionMode | None = None
    course_id: str | None = None

    def __post_init__(self) -> None:
        # Validate the credibility bound at acquisition so a bad score fails here, not deep in the
        # store's Citation construction (which enforces the same [0, 1] at the wire boundary).
        if self.credibility is not None and not 0.0 <= self.credibility <= 1.0:
            raise ValueError(f"credibility must be in [0, 1], got {self.credibility}")
