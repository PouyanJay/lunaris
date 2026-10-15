from dataclasses import dataclass
from typing import Self

from .resource_kind import ResourceKind


@dataclass(frozen=True)
class GovernedResources:
    """The prod resources the power switch stops and starts.

    Never includes the control plane (``lunaris-prod-control``): it serves the switch, so stopping
    it would leave no way to turn production back on.
    """

    container_apps: tuple[str, ...]
    virtual_machines: tuple[str, ...]

    @classmethod
    def prod_default(cls) -> Self:
        """Every billable prod workload in ``rg-lunaris-prod``."""
        return cls(
            container_apps=(
                "lunaris-prod-api",
                "lunaris-prod-video-worker",
                "lunaris-prod-inference",
                "lunaris-prod-embeddings",
                "lunaris-prod-cover-worker",
                "lunaris-prod-copilot",
            ),
            # The simulator supervisor host, the single largest prod cost when left running.
            virtual_machines=("lunaris-prod-sim-worker",),
        )

    def members(self) -> tuple[tuple[str, ResourceKind], ...]:
        """Every governed resource with its kind: container apps first, then virtual machines."""
        return tuple((app, ResourceKind.CONTAINER_APP) for app in self.container_apps) + tuple(
            (vm, ResourceKind.VIRTUAL_MACHINE) for vm in self.virtual_machines
        )
