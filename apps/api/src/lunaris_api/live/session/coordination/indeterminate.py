from ...work_refused import LiveWorkRefusedError


class IndeterminateLiveTurnError(LiveWorkRefusedError):
    status_code = 409
    detail = (
        "This turn's result could not be confirmed. Reload the session; "
        "it will not be charged again automatically."
    )
