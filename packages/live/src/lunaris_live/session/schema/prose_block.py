from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .layout_component import LayoutComponent


class ProseBlock(LiveModel):
    """Where the tutor's words go. A slot: the words themselves are ``SessionTurn.tutor``.

    Carrying the lesson text here as well would put two copies of it on the turn, and the surface
    would then be free to render one while the transcript stored the other.
    """

    component: Literal[LayoutComponent.PROSE] = LayoutComponent.PROSE
    id: str = Field(min_length=1, max_length=60)
