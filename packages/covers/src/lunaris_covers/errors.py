class CoverPipelineError(Exception):
    """A cover-generation failure the pipeline raises.

    ``user_detail`` — when set — is an owner-safe reason the worker writes onto the job row (the
    reader shows it); without one, the worker surfaces only the exception class name and keeps the
    full exception in the logs. Mirrors ``VideoPipelineError``.
    """

    def __init__(self, message: str, *, user_detail: str | None = None) -> None:
        super().__init__(message)
        self.user_detail = user_detail
