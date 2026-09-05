from collections.abc import Sequence
from typing import Protocol

from ...graph.schema import ConceptNode, MasteryCriterion
from ..schema import PriorAttempt, TurnGrade


class IGrader(Protocol):
    """Scores a free-text answer against the one criterion it was asked to meet.

    Separate from the tutor on purpose (U1). A tutor scoring its own teaching is the teacher marking
    its own homework, and the learner model — which decides what gets skipped — would be built on
    that bias. Rejected for the same reason: asking the learner to rate themselves, which is poorly
    correlated with mastery and makes them do the system's job.

    ``criterion`` is passed rather than looked up from ``node``: the map can grow and change
    mid-session (C1), so the thing being graded has to be the thing that was actually staged. The
    node comes too, because a criterion read without its concept is a sentence with no subject.

    ``previously`` is what this learner already tried against this same criterion, in order, with
    the verdicts they were given (T8). It exists so the grader can be consistent with itself: an
    answer marked "partial, you are missing X" and a later answer that adds X must not score lower.
    Optional with an empty default, because the first attempt at anything has no history and every
    stub grader predates it.
    """

    async def grade(
        self,
        answer: str,
        *,
        criterion: MasteryCriterion,
        node: ConceptNode,
        run_id: str,
        previously: Sequence[PriorAttempt] = (),
    ) -> TurnGrade: ...
