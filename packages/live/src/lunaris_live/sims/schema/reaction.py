from typing import Annotated

from pydantic import Field

from ...graph.schema.base import LiveModel


class SimReaction(LiveModel):
    """Tutor words and a validated complete control state, never a mastery verdict."""

    text: str = Field(min_length=1, max_length=2000)
    state: dict[str, Annotated[float, Field(strict=True, allow_inf_nan=False)]] = Field(
        min_length=1, max_length=8
    )
