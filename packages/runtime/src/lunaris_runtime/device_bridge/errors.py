"""The device bridge's failure mode: the learner's device stopped serving the build."""


class DeviceBridgeDisconnectedError(Exception):
    """Raised to the model side when a device-compute completion can never be served: the tab
    went silent past the liveness bound, a claimed completion was never answered, or the run was
    torn down. The build fails promptly with this — a hung run is the one unacceptable outcome
    (the web surfaces it as "keep this tab open")."""
