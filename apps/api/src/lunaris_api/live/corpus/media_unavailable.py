from ..work_refused import LiveWorkRefusedError


class MaterialUnavailableError(LiveWorkRefusedError):
    status_code = 404
    detail = "This material is unavailable."
