from enum import StrEnum


class TeachingDepth(StrEnum):
    """How far into a concept a session should go.

    Not a difficulty rating — a *stance*. The same concept is taught differently depending on
    whether the learner needs a feel for it, needs to derive it, or needs to use it on Monday.
    """

    INTUITION_FIRST = "intuition_first"
    FORMAL = "formal"
    APPLIED = "applied"
