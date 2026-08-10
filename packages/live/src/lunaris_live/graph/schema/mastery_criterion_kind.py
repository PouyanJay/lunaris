from enum import StrEnum


class MasteryCriterionKind(StrEnum):
    """The shape of evidence a criterion asks for.

    Each kind maps to something the runtime can actually stage: PREDICT to a question with a
    checkable answer, MANIPULATE to a simulator milestone, EXPLAIN to teaching it back. That
    mapping is why mastery is written as things to *do* — it is what makes assessment generatable
    rather than hand-authored.
    """

    PREDICT = "predict"
    MANIPULATE = "manipulate"
    EXPLAIN = "explain"
