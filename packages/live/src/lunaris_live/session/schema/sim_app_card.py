from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from ...graph.schema.mastery_criterion_kind import MasteryCriterionKind
from .surface_kind import SurfaceKind


class SimAppCard(LiveModel):
    """A simulator mounted in place, and the do-statement it exists to let the learner demonstrate.

    Tier 3 (plan §8). The difference from every other card is *where the evidence comes from*: the
    learner acts in the frame rather than writing, and the simulator reports what they did. That
    report then goes in through the ordinary answer path and is graded by the same separate grader
    against ``statement`` — so this is a new surface and not a new way to be assessed.

    ``statement`` is the criterion's own words, copied verbatim for the same reason
    ``CriterionCard`` copies them: a learner marked against one wording and shown another has been
    assessed on something they were never asked.
    """

    kind: Literal[SurfaceKind.SIM_APP] = SurfaceKind.SIM_APP
    node_id: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    #: Which simulator, and what to call it. Carried rather than referenced by id alone so a stored
    #: turn still says what the learner was shown after the registry has moved on.
    app_id: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=200)
    #: The criterion's own words (U1).
    statement: str = Field(min_length=1, max_length=500)
    #: What shape of evidence this asks for. Always a doing-shaped one in practice — a criterion
    #: that needed a simulator to demonstrate is not one somebody explains their way through.
    asks: MasteryCriterionKind
