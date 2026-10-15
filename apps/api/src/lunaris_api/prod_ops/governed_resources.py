from dataclasses import dataclass


@dataclass(frozen=True)
class GovernedResources:
    """The prod resources the power switch stops and starts.

    Never includes the control plane (``lunaris-prod-control``): it serves the switch, so stopping
    it would leave no way to turn production back on.
    """

    container_apps: tuple[str, ...]
    virtual_machines: tuple[str, ...]

    @classmethod
    def prod_default(cls) -> "GovernedResources":
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
            virtual_machines=(),
        )
