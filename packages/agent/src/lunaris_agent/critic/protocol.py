from typing import Protocol

from lunaris_runtime.schema import Course


class ICritic(Protocol):
    """Reviews a built course and returns structural/pedagogical issues.

    An empty list means the course passes the critic and may be published. The MVP impl
    is a deterministic structural rubric; a richer LLM-as-judge critic is a V1 refinement.
    """

    def review(self, course: Course) -> list[str]: ...
