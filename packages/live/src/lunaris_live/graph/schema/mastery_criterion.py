from pydantic import Field

from .base import LiveModel
from .mastery_criterion_kind import MasteryCriterionKind


class MasteryCriterion(LiveModel):
    """One thing the learner must be able to DO to have understood a concept.

    Deliberately not "knows that…": a statement of knowledge cannot be checked, while a statement
    of action can be staged, watched and scored. This is backward design, and it is what lets later
    phases generate the check instead of an author writing it.
    """

    kind: MasteryCriterionKind
    #: The do-statement itself, addressed to the learner.
    statement: str = Field(min_length=1, max_length=500)
    #: True when demonstrating this needs an interactive simulator (Phase 3). The criterion is still
    #: recorded now — knowing what a concept *would* need is what tells Phase 3 which sims to build.
    needs_sim: bool = False
