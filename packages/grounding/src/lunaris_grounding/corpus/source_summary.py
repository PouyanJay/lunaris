from dataclasses import dataclass

from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier


@dataclass(frozen=True)
class CorpusSourceSummary:
    """A source-level view of the corpus (P6.1): one ingested source folded back from its chunks.

    The corpus stores chunks, not sources, so a "source" is the chunks that share a ``source_id``.
    This summary is what the Corpus UI lists and what per-source delete targets — the provenance
    a learner curates, with ``chunk_count`` showing how much the source contributes.
    """

    source_id: str
    course_id: str | None
    title: str | None
    url: str | None
    source_type: SourceType | None
    trust_tier: TrustTier | None
    credibility: float | None
    acquisition_mode: AcquisitionMode | None
    fetched_at: str | None
    chunk_count: int
