from typing import Protocol

from ...graph.schema import ConceptNode, MasteryCriterion
from ..schema import TurnGrade


class IGrader(Protocol):
    """Scores a free-text answer against the one criterion it was asked to meet.

    Separate from the tutor on purpose (U1). A tutor scoring its own teaching is the teacher marking
    its own homework, and the learner model — which decides what gets skipped — would be built on
    that bias. Rejected for the same reason: asking the learner to rate themselves, which is poorly
    correlated with mastery and makes them do the system's job.

    ``criterion`` is passed rather than looked up from ``node``: the map can grow and change
    mid-session (C1), so the thing being graded has to be the thing that was actually staged. The
    node comes too, because a criterion read without its concept is a sentence with no subject.
    """

    async def grade(
        self, answer: str, *, criterion: MasteryCriterion, node: ConceptNode, run_id: str
    ) -> TurnGrade: ...
