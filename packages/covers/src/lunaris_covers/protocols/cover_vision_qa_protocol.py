from typing import Protocol

from lunaris_covers.models.cover_brief import CoverBrief
from lunaris_covers.schemas.cover_qa_verdict import CoverQaVerdict


class ICoverVisionQa(Protocol):
    """Judges a rendered cover against the house-style rubric — the anti-slop gate.

    The default implementation prompts a vision-capable Claude with the locked constraints and the
    rendered image and parses a structured verdict; the seam keeps the pipeline provider-agnostic
    and testable against a scripted inspector. ``model`` is the Claude model id, surfaced so the
    pipeline records it in provenance (the QA model).
    """

    @property
    def model(self) -> str: ...

    async def inspect(self, image: bytes, brief: CoverBrief) -> CoverQaVerdict: ...
