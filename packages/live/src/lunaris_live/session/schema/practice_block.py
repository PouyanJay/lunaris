from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .layout_component import LayoutComponent


class PracticeBlock(LiveModel):
    """Prompts to think through before answering — as many as the estimate calls for.

    Plan §8's third named Tier 2 behaviour — *"practice scaffolding sized to the knowledge
    estimate"*. Sized, not merely present or absent, which is why this holds a list rather than a
    single prompt and a boolean.

    Nothing here is graded, and that is the line between this tier and Tier 1. These prompts move no
    belief: the evidence still comes from the staged criterion answered in the card (U1), so a
    scaffold that happened to be badly written costs a learner a moment rather than a mark.
    """

    component: Literal[LayoutComponent.PRACTICE] = LayoutComponent.PRACTICE
    id: str = Field(min_length=1, max_length=60)
    prompts: list[str] = Field(min_length=1)
