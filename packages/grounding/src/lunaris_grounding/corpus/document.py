from dataclasses import dataclass

from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier


@dataclass(frozen=True)
class GroundingDocument:
    """A single embedded corpus chunk: the text, its vector, and source provenance.

    ``id`` is deterministic (a hash of kc + content) so re-ingesting the same source is
    idempotent. ``embedding`` is stored as a tuple to keep the entity immutable.

    The trust/provenance set (P6.0) carried over from the ``CandidateSource``: ``trust_tier`` +
    ``credibility`` + ``source_type`` (graded evidence, surfaced on the citation), ``fetched_at`` +
    ``acquisition_mode`` (audit provenance), and ``course_id`` (the per-course scope the retriever
    filters on). All optional so an un-classified chunk still stores.
    """

    id: str
    kc_id: str
    content: str
    embedding: tuple[float, ...]
    title: str | None = None
    url: str | None = None
    run_id: str | None = None
    source_type: SourceType | None = None
    trust_tier: TrustTier | None = None
    credibility: float | None = None
    fetched_at: str | None = None
    acquisition_mode: AcquisitionMode | None = None
    course_id: str | None = None
    source_id: str | None = None  # the source this chunk came from (P6.1); shared across its chunks

    def __post_init__(self) -> None:
        # Mirror CandidateSource: keep the [0, 1] credibility bound an invariant of the entity.
        if self.credibility is not None and not 0.0 <= self.credibility <= 1.0:
            raise ValueError(f"credibility must be in [0, 1], got {self.credibility}")
