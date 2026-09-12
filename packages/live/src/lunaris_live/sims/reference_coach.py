from .schema.contract import SimContract
from .schema.event import SimEvent
from .schema.reaction import SimReaction


class ReferenceSimCoach:
    """Offline walking-skeleton coach: contrast the learner's chosen position with a boundary."""

    async def respond(self, contract: SimContract, event: SimEvent, *, run_id: str) -> SimReaction:
        name, parameter = next(iter(contract.parameters.items()))
        target = parameter.minimum if event.state[name] != parameter.minimum else parameter.maximum
        return SimReaction(
            text=f"You set {parameter.label} to {event.state[name]:g}. "
            f"I moved it to {target:g}. What changed, and why?",
            state={**event.state, name: target},
        )
