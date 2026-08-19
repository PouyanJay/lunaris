from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .surface_kind import SurfaceKind


class ExplainBack(LiveModel):
    """A place to say it back, with nothing to recognise.

    Deliberately optionless. Retrieval only strengthens a memory if the learner produces it, so a
    card offering choices would let recognition stand in for recall — the one substitution that
    makes the move pointless while still looking like it worked.
    """

    kind: Literal[SurfaceKind.EXPLAIN_BACK] = SurfaceKind.EXPLAIN_BACK
    node_id: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=500)
