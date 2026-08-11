from enum import StrEnum


class EvidenceKind(StrEnum):
    """What one graded answer said about the learner.

    Three values, not a score: the grader is judging a free-text answer against one explicit
    do-statement, and asking it for 0.73 would be asking for a precision it does not have. Three
    verdicts are what a grader can defend and what a tutor can act on — "nearly" is a different
    teaching move from "no", which is why PARTIAL exists rather than collapsing into a neighbour.
    """

    MET = "met"
    PARTIAL = "partial"
    NOT_MET = "not_met"
