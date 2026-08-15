from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .layout_component import LayoutComponent


class SurfaceBlock(LiveModel):
    """Where the director's Tier 1 card goes. A slot: the card itself is ``SessionTurn.surface``.

    This is the seam between the two tiers, and it is deliberately empty. Tier 1 is deterministic
    *because these components feed the learner model* (plan §8); a layout that could restate the
    card's props would be a second, generative path to the thing the learner is assessed by.
    """

    component: Literal[LayoutComponent.SURFACE] = LayoutComponent.SURFACE
    id: str = Field(min_length=1, max_length=60)
