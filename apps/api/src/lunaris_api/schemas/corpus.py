from typing import Literal, Self

from lunaris_grounding import CorpusSourceSummary
from lunaris_runtime.schema import AcquisitionMode, SourceType, TrustTier
from pydantic import Field, model_validator

from ..corpus_service import IngestOutcome
from .base import CamelModel


class CorpusSourceRequest(CamelModel):
    """Request body for adding a pasted-text or URL source to a course corpus (P6.1 manual mode).

    ``kind`` discriminates: ``text`` carries ``text``; ``url`` carries ``url``. File uploads go to
    the separate multipart ``/sources/file`` endpoint (binary bodies aren't JSON).
    """

    course_id: str = Field(min_length=1)
    kind: Literal["text", "url"]
    title: str | None = Field(default=None, max_length=300)
    text: str | None = Field(default=None, max_length=200_000)
    url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _payload_matches_kind(self) -> Self:
        if self.kind == "text" and not (self.text and self.text.strip()):
            raise ValueError("kind 'text' requires non-empty text")
        if self.kind == "url":
            if not (self.url and self.url.strip()):
                raise ValueError("kind 'url' requires a url")
            # Reject non-http(s) schemes at the boundary (file://, ftp://, javascript:, …) so they
            # never reach the fetcher; internal-IP/denylist SSRF is caught in the service via
            # classify_domain (the shared discovery guard).
            if not self.url.strip().lower().startswith(("http://", "https://")):
                raise ValueError("url must be http(s)")
        return self


class IngestResultView(CamelModel):
    """The gate's verdict for a submitted source, on the wire (camelCase)."""

    accepted: bool
    source_id: str
    chunks: int
    reason: str | None = None

    @classmethod
    def of(cls, outcome: IngestOutcome) -> "IngestResultView":
        return cls(
            accepted=outcome.accepted,
            source_id=outcome.source_id,
            chunks=outcome.chunks,
            reason=outcome.reason,
        )


class CorpusSourceView(CamelModel):
    """A source-level row of the corpus, on the wire (camelCase) — what the Corpus UI lists.

    The enum fields keep their types (Pydantic serialises a ``StrEnum`` to its string value), so the
    wire stays in lockstep with the domain vocabulary without manual ``.value`` mapping.
    """

    source_id: str
    course_id: str | None = None
    title: str | None = None
    url: str | None = None
    source_type: SourceType | None = None
    trust_tier: TrustTier | None = None
    credibility: float | None = None
    acquisition_mode: AcquisitionMode | None = None
    fetched_at: str | None = None
    chunk_count: int

    @classmethod
    def of(cls, summary: CorpusSourceSummary) -> "CorpusSourceView":
        return cls(
            source_id=summary.source_id,
            course_id=summary.course_id,
            title=summary.title,
            url=summary.url,
            source_type=summary.source_type,
            trust_tier=summary.trust_tier,
            credibility=summary.credibility,
            acquisition_mode=summary.acquisition_mode,
            fetched_at=summary.fetched_at,
            chunk_count=summary.chunk_count,
        )
