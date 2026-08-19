from pydantic import Field

from ...graph.schema.base import LiveModel
from ..max_answer_chars import MAX_ANSWER_CHARS


class InterviewExchange(LiveModel):
    """One question the interviewer asked and what the learner said back (P2c).

    The interviewer is handed the exchanges so far rather than the session, for the same reason
    the tutor is handed ``already_said`` rather than the transcript: it should be able to ask the
    next question without knowing what a turn is, and a stub narrower than the protocol should
    fail on the shape it was actually given.
    """

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
