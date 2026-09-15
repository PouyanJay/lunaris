from ..work_refused import LiveWorkRefusedError


class CorpusInvalidError(LiveWorkRefusedError, ValueError):
    status_code = 422
    detail = "Course material is incomplete, exceeds source limits, or has invalid references."
