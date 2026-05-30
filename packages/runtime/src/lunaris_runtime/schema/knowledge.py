from pydantic import Field

from .base import CourseModel
from .enums import BloomLevel


class Citation(CourseModel):
    """A grounding source. Referenced elsewhere by its `id`."""

    id: str
    title: str | None = None
    url: str | None = None
    snippet: str | None = None


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
