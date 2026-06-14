class VideoPipelineError(Exception):
    """Base for every failure the video pipeline raises — the worker settles the job FAILED.

    ``user_detail`` is an optional plain-language, owner-safe reason the worker puts on the job row
    (the reader's failed state shows it). When ``None`` the worker falls back to the exception class
    name only — never leaking an internal message. Set it on the few failures a user can act on
    (e.g. narration that won't sync after a retry: "turn off narration for a silent version").
    """

    def __init__(self, message: str, *, user_detail: str | None = None) -> None:
        super().__init__(message)
        self.user_detail = user_detail
