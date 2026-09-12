from typing import Protocol

from ..schema.contract import SimContract
from ..schema.event import SimEvent
from ..schema.reaction import SimReaction


class ISimCoach(Protocol):
    """A bounded teaching response to validated simulator input; grading remains separate."""

    async def respond(
        self, contract: SimContract, event: SimEvent, *, run_id: str
    ) -> SimReaction: ...
