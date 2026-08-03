from pydantic import Field

from .base import LiveModel
from .concept_node import ConceptNode


class ConceptGraph(LiveModel):
    """A topic's concept map: what it is made of, and what has to be learned before what.

    Deliberately **not** an immutable build artifact. A session steers where the learner takes it,
    so the graph grows at runtime (C1): ``version`` is bumped by every extension, and the map of
    the subject outlives any one route through it.

    Edges live on the nodes as ``requires`` rather than in a parallel edge list — one representation
    that cannot disagree with itself. ``topo_order`` and ``is_acyclic`` are *derived*: they are set
    by assembly, never authored by a compiler, which is what stops a model's output from asserting
    its own correctness.
    """

    graph_id: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=200)
    #: Bumped on every runtime extension; 1 for a freshly compiled graph.
    version: int = Field(default=1, ge=1)
    nodes: list[ConceptNode] = Field(default_factory=list)
    #: Derived by assembly — every node id, prerequisites first.
    topo_order: list[str] = Field(default_factory=list)
    #: Derived by assembly. False until assembly has proved otherwise.
    is_acyclic: bool = False
