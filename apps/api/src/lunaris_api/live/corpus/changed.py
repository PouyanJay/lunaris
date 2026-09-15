from ..work_refused import LiveWorkRefusedError


class CorpusChangedError(LiveWorkRefusedError):
    status_code = 409
    detail = "This course has changed. Prepare it in Live again to use its current material."
