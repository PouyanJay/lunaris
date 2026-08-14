from enum import StrEnum


class SurfaceKind(StrEnum):
    """Which Tier 1 component a turn puts in front of the learner.

    A closed set, for the same reason ``MoveKind`` is one: these components *feed the learner model*
    (plan §8), so the set of instruments a learner can be assessed by is a pedagogical decision and
    not something that should be able to grow by accident. Adding a sixth is a deliberate change
    here that every renderer is forced to notice.
    """

    #: The staged do-statement, answered in the learner's own prose. U1's evidence surface.
    CRITERION_CARD = "criterion_card"
    #: The concept's authored misconceptions, with the truth among them, for a learner who is stuck.
    QUIZ_CARD = "quiz_card"
    #: Produce it from memory rather than recognise it — what a retrieval move is for.
    EXPLAIN_BACK = "explain_back"
    #: What the learner demonstrated, shown when the session ends.
    MASTERY_METER = "mastery_meter"
    #: Where a concept sits, for the case this session cannot check it at all.
    CONCEPT_MAP = "concept_map"
