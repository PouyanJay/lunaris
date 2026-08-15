from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .layout_component import LayoutComponent


class HintBlock(LiveModel):
    """One hint, behind a disclosure the learner opens or does not.

    Plan §8's second named Tier 2 behaviour — *"hint drawer suppressed at high confidence"*. The
    suppression is the point: a hint offered to somebody who has the concept is noise at best, and
    at worst it tells them the system does not believe them.

    Closed by construction rather than by a flag. A hint that opens itself is not a hint, it is the
    answer moved up the page, and the whole value of the drawer is that reaching for it is the
    learner's decision.
    """

    component: Literal[LayoutComponent.HINT] = LayoutComponent.HINT
    id: str = Field(min_length=1, max_length=60)
    hint: str = Field(min_length=1, max_length=500)
