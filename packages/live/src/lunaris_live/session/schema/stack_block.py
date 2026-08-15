from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .layout_component import LayoutComponent


class StackBlock(LiveModel):
    """Children stacked in reading order — the only arranging this catalog does.

    One layout primitive and not a grid, a row or a splitter: Tier 2 varies *what is shown and in
    what order*, which is what plan §8 asks of it, and every extra axis of freedom is another way a
    composition can be laid out badly on a phone with nobody looking.
    """

    component: Literal[LayoutComponent.STACK] = LayoutComponent.STACK
    id: str = Field(min_length=1, max_length=60)
    #: Ids of the blocks in this stack, in the order they are read. Flat references rather than
    #: nesting, which is A2UI v0.9's own shape — a tree that is a list is one a stream can build
    #: incrementally and one a renderer cannot recurse infinitely through.
    children: list[str] = Field(default_factory=list)
