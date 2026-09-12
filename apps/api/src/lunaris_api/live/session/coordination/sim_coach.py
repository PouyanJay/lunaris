import json

from lunaris_live.session import Session
from lunaris_live.sims.protocols.coach import ISimCoach
from lunaris_live.sims.schema.contract import SimContract
from lunaris_live.sims.schema.event import SimEvent
from lunaris_live.sims.schema.reaction import SimReaction

from .coordinator import SessionCoordinator


class AdmittedSimCoach:
    """Only a new validated gesture reaches paid admission; replay remains free."""

    def __init__(self, coach: ISimCoach, coordinator: SessionCoordinator, session: Session) -> None:
        self._coach, self._coordinator, self._session = coach, coordinator, session

    async def respond(self, contract: SimContract, event: SimEvent, *, run_id: str) -> SimReaction:
        await self._coordinator.paid(
            self._session, "sim:" + json.dumps(event.model_dump(mode="json"), sort_keys=True)
        )
        return await self._coach.respond(contract, event, run_id=run_id)
