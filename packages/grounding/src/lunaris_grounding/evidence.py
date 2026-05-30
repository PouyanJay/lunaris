from dataclasses import dataclass

from lunaris_runtime.schema import Citation


@dataclass(frozen=True)
class Evidence:
    """A retrieved piece of evidence for a claim: a citation plus its relevance score."""

    citation: Citation
    score: float


@dataclass(frozen=True)
class Support:
    """An independent assessor's verdict on whether evidence supports a claim.

    ``citation_id`` is the evidence that best supports the claim (None if unsupported).
    """

    score: float
    citation_id: str | None = None
