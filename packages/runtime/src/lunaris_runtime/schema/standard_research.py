from typing import Self

from pydantic import Field, model_validator

from .base import CourseModel
from .enums import ResearchStatus, TrustTier


class ResearchSource(CourseModel):
    """One vetted source the research stage grounded the brief against (P7.2).

    Structural provenance: ``url`` + ``fetched_at`` + ``trust_tier`` are constructed where the page
    is acquired, not at the call site, and flow untouched to the reader so a learner can audit where
    a target came from (``"per canada.ca"``). ``fetched_at`` is an ISO-8601 instant.
    """

    url: str
    title: str = ""
    trust_tier: TrustTier = TrustTier.OPEN
    fetched_at: str = ""


class StandardResearch(CourseModel):
    """The researched grounding for a brief's target standard (the brief's ``research`` block).

    A bounded, best-effort research step distils the *real* competency descriptors and any
    score/threshold lines of the target standard from authoritative sources, with provenance, so
    extraction and the curriculum design backward from the actual standard rather than the model's
    approximate memory. ``status`` records how well grounding succeeded (it degrades honestly when
    no key/source is available); ``sources`` is empty exactly when grounding was ``UNAVAILABLE``.
    """

    status: ResearchStatus = ResearchStatus.UNAVAILABLE
    competencies: list[str] = Field(default_factory=list)
    score_table: list[str] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sources_consistent_with_status(self) -> Self:
        """Keep the status honest about provenance: research is never ``COMPLETE`` without a source
        to cite, and ``UNAVAILABLE`` (no usable source) must carry none — so a competency can't be
        labelled grounded when it actually came from the model's memory."""
        if self.status is ResearchStatus.COMPLETE and not self.sources:
            raise ValueError("COMPLETE research must cite at least one source")
        if self.status is ResearchStatus.UNAVAILABLE and self.sources:
            raise ValueError("UNAVAILABLE research must carry no sources")
        return self
