from pydantic import Field

from .base import CourseModel
from .enums import BloomLevel, SourceType, TrustTier


class Citation(CourseModel):
    """A grounding source. Referenced elsewhere by its `id`.

    Carries the trust/provenance the verifier's chosen evidence was graded on (P6.0): ``trust_tier``
    (where the source sits in the authority order), ``credibility`` (a 0..1 blended quality score),
    ``source_type`` (what kind of source it is), and ``fetched_at`` (when it was acquired). All
    optional — a citation with no classification (a pre-P6.0 course, or evidence from an un-tiered
    stub) renders without a trust badge rather than falsely claiming a tier. Constructed at the
    corpus and flow untouched to the reader (provenance-is-structural).
    """

    id: str
    title: str | None = None
    url: str | None = None
    snippet: str | None = None
    trust_tier: TrustTier | None = None
    credibility: float | None = Field(default=None, ge=0, le=1)
    source_type: SourceType | None = None
    fetched_at: str | None = None  # ISO-8601 instant, stamped at acquisition


class KnowledgeComponent(CourseModel):
    """The atomic teachable unit (KC)."""

    id: str
    label: str
    definition: str
    difficulty: float = Field(ge=0, le=1)
    bloom_ceiling: BloomLevel
    sources: list[str] = Field(default_factory=list)  # Citation ids


class Edge(CourseModel):
    """`from_` must be learned before `to`."""

    from_: str = Field(alias="from")
    to: str
    strength: float = Field(ge=0, le=1)


class PrerequisiteGraph(CourseModel):
    """The correctness object (build-spec §07). Assembled deterministically."""

    nodes: list[KnowledgeComponent] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    frontier: list[str] = Field(default_factory=list)  # learner's known boundary
    is_acyclic: bool = False
    topo_order: list[str] = Field(default_factory=list)
