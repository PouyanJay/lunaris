"""What Live declines to start, and how every refusal reaches a learner.

Its own module because both planes raise it: the compile plane rations maps and extensions, the
session plane rations sittings and their spend. Leaving the base in the compile plane's throttle
would have the session plane import a graph module for a class about neither.
"""


class LiveWorkRefusedError(Exception):
    """Base for work Live declines to start.

    Subclasses set two class attributes the routers read so EVERY refusal maps the same way (one
    ``except`` clause, no per-reason branching): ``status_code`` and ``detail``, the learner-facing
    sentence. The base seeds the exception message from ``detail`` so logs carry the reason rather
    than a blank ``SomeError:``.
    """

    status_code: int = 429
    detail: str = "Live can't take that on right now."

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.detail)
