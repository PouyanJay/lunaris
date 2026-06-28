from dataclasses import dataclass


@dataclass(frozen=True)
class AppPower:
    """One prod container app's run state: its name and whether it is running (vs stopped).

    Tightly coupled to ``PowerState`` (its container), so they share a module.
    """

    name: str
    running: bool


@dataclass(frozen=True)
class PowerState:
    """Whether production is on, and the run state of each prod app behind that.

    ``is_on`` is the headline the switch reflects — true when the environment is serving (the API
    app is running); ``apps`` lists every app the on/off action governs, so the admin sees exactly
    what is up or stopped.
    """

    is_on: bool
    apps: tuple[AppPower, ...]
