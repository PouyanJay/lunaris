from ..work_refused import LiveWorkRefusedError


class CorpusUnavailableError(LiveWorkRefusedError):
    status_code = 404
    detail = "Course is unavailable."
