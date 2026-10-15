from enum import StrEnum


class PowerStatus(StrEnum):
    """Where one governed resource stands. Start and stop are asynchronous on Azure, so a resource
    spends a while ``TRANSITIONING`` between the two settled states."""

    RUNNING = "running"
    STOPPED = "stopped"
    TRANSITIONING = "transitioning"
