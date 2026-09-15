from ..work_refused import LiveWorkRefusedError


class GraphNotReadyError(LiveWorkRefusedError):
    status_code = 409
    detail = "This map is awaiting source verification."
