from enum import StrEnum

from pydantic import Field

from ...graph.schema.base import LiveModel


class CoveredOutcome(StrEnum):
    """How a concept the session touched stands as it ends — the words the recap is briefed with."""

    #: The belief is over the mastery bar: they showed it.
    DEMONSTRATED = "demonstrated"
    #: Graded at least once and not there yet: worth coming back to first.
    FORMING = "forming"
    #: Taught, never graded (a concept nothing could check, or a turn left unanswered).
    INTRODUCED = "introduced"


class Covered(LiveModel):
    """One concept the session touched, as the recap is told about it (P2c T5).

    Built deterministically from the transcript and the belief — never from the tutor's own words
    about what happened, so the recap is briefed with the record and can only dress it, not revise
    it. ``CoveredOutcome`` is its own enum, and the two are tightly coupled siblings.
    """

    node_id: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    outcome: CoveredOutcome
    evidence_count: int = Field(ge=0)
