from dataclasses import dataclass

from .power_status import PowerStatus
from .resource_kind import ResourceKind


@dataclass(frozen=True)
class ResourcePower:
    """One governed prod resource's run state.

    Tightly coupled to ``PowerState`` (its container), so they share a module.
    """

    name: str
    kind: ResourceKind
    status: PowerStatus

    @property
    def running(self) -> bool:
        return self.status is PowerStatus.RUNNING


@dataclass(frozen=True)
class PowerState:
    """Whether production is on, and the run state of each prod resource behind that.

    ``is_on`` is the headline the switch reflects: true when the environment is serving (the API app
    is running). ``resources`` lists everything the on/off action governs, so the admin sees exactly
    what is up, down, or still changing; ``settled`` is false while any of them is mid-transition.
    """

    is_on: bool
    resources: tuple[ResourcePower, ...]

    @property
    def settled(self) -> bool:
        return all(r.status is not PowerStatus.TRANSITIONING for r in self.resources)
