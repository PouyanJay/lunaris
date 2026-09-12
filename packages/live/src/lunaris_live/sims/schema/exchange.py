from pydantic import Field

from ...graph.schema.base import LiveModel
from .event import SimEvent
from .reaction import SimReaction


class SimExchange(LiveModel):
    """Persisted interaction; the same response can be recovered without calling the tutor again."""

    event: SimEvent
    reaction: SimReaction
    run_id: str = Field(min_length=1, max_length=100)
