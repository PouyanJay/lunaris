from enum import StrEnum


class ResourceKind(StrEnum):
    """What kind of Azure resource the power switch governs; each has its own start/stop actions."""

    CONTAINER_APP = "container_app"
    VIRTUAL_MACHINE = "virtual_machine"
