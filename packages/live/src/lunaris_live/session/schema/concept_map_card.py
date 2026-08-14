from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .surface_kind import SurfaceKind


class ConceptMapCard(LiveModel):
    """Where a concept sits, for a turn this session cannot check.

    The honest surface for a concept whose every criterion needs a simulator (Phase 3): nothing the
    learner says next can move a belief, so a card shaped like an assessment would be collecting an
    answer that is scored against nothing.

    Prerequisites are **names**, read off the map's own chain (P1's ``prerequisites_of``, the C2
    query built for exactly this), so a renderer needs no graph of its own and cannot disagree with
    the one the session is walking.
    """

    kind: Literal[SurfaceKind.CONCEPT_MAP] = SurfaceKind.CONCEPT_MAP
    focus_node_id: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    #: Everything this concept needs first, in the order the map teaches them.
    prerequisites: list[str] = Field(default_factory=list)
