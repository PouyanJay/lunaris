from pydantic import Field

from .base import LiveModel
from .teaching_depth import TeachingDepth


class TeachingSpec(LiveModel):
    """How a concept should be taught — the part of a node a tutor reads before opening its mouth.

    ``misconceptions`` is the load-bearing field. A tutor that only knows what is true teaches at
    the learner; one that knows how people usually get this wrong can go looking for the specific
    wrong model in front of it, which is most of what makes a session feel like tutoring.
    """

    objective: str = Field(min_length=1, max_length=500)
    #: The wrong models learners commonly hold about this concept, each stated as the learner
    #: would believe it — not as a correction.
    misconceptions: list[str] = Field(default_factory=list)
    depth: TeachingDepth = TeachingDepth.INTUITION_FIRST
