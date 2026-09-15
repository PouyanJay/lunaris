from ..work_refused import LiveWorkRefusedError


class MaterialStaleError(LiveWorkRefusedError):
    status_code = 409
    detail = "This session has moved on or expired. Open the current session material."
