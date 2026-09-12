from ...work_refused import LiveWorkRefusedError


class LiveGraphBusyError(LiveWorkRefusedError):
    status_code = 409
    detail = "An operation on this topic is still finishing. Give it a moment, then reload."
