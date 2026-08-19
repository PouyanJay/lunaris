from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from ...graph.schema.mastery_criterion_kind import MasteryCriterionKind
from .surface_kind import SurfaceKind


class CriterionCard(LiveModel):
    """The do-statement the turn staged, shown as the thing the learner will be marked on.

    The statement is copied verbatim rather than paraphrased for the surface. A learner marked
    against one wording and shown another has been assessed on something they were never asked, and
    the grader's verdict would look arbitrary to them — which is the fastest way to lose the trust
    the whole loop depends on.
    """

    kind: Literal[SurfaceKind.CRITERION_CARD] = SurfaceKind.CRITERION_CARD
    node_id: str = Field(min_length=1, max_length=100)
    #: The concept's name, so the card reads as being about something rather than about an id.
    concept: str = Field(min_length=1, max_length=200)
    #: The criterion's own words (U1).
    statement: str = Field(min_length=1, max_length=500)
    #: What shape of evidence this asks for, so a renderer can size the answer control to it.
    asks: MasteryCriterionKind
