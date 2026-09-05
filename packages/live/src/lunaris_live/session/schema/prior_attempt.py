from pydantic import Field

from ...graph.schema.base import LiveModel
from ..max_answer_chars import MAX_ANSWER_CHARS
from .evidence_kind import EvidenceKind


class PriorAttempt(LiveModel):
    """What the learner already said about this criterion, and what it was judged to show (T8).

    Carried into the grader so it can be consistent with itself. Each answer used to be marked in
    isolation, and the first real session showed what that costs: an answer was told it was missing
    "adjusts many small numbers", a later answer said exactly that, and it scored *lower*. A grader
    that punishes a learner for following its own feedback teaches them to ignore the feedback,
    which is the one thing feedback cannot survive.

    Deliberately just the words and the verdict, not the reason: the reason was addressed to the
    learner, and feeding a model its own prose back is how a grader talks itself into a position
    rather than re-reading the answer.
    """

    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
    kind: EvidenceKind
