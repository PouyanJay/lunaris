from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .layout_component import LayoutComponent


class ExampleBlock(LiveModel):
    """A worked example, open or closed.

    Plan §8's first named Tier 2 behaviour — *"worked example expanded or collapsed"*. Whether it
    appears at all, and whether it opens open, is decided from the knowledge estimate by
    ``compose_layout``; what is *in* it is the tutor's, unedited.
    """

    component: Literal[LayoutComponent.WORKED_EXAMPLE] = LayoutComponent.WORKED_EXAMPLE
    id: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=200)
    steps: list[str] = Field(min_length=1)
    #: Whether the example is open when the turn is drawn. Not a client preference: a learner new to
    #: a concept should not have to discover that the help exists, and one who has it should not
    #: have to fold it away.
    expanded: bool = False
