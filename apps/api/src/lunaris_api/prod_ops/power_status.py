from enum import StrEnum


class PowerStatus(StrEnum):
    """Where one governed resource stands. Start and stop are asynchronous on Azure, so a resource
    spends a while ``TRANSITIONING`` between the two settled states. ``UNKNOWN`` is a state Azure
    reported that is neither (or no state at all); it counts as settled, so a watcher stops waiting
    and shows it rather than polling for a transition that is not coming."""

    RUNNING = "running"
    STOPPED = "stopped"
    TRANSITIONING = "transitioning"
    UNKNOWN = "unknown"
