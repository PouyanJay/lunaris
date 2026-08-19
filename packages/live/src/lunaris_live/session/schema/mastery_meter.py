from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .surface_kind import SurfaceKind


class MeterEntry(LiveModel):
    """One concept's standing, as the learner is shown it.

    ``recall`` is the *decayed* belief — what they are believed to know now — rather than the stored
    estimate, which is the belief at its last evidence. Showing the undecayed number would tell
    somebody they still hold a concept they last touched forty minutes and six concepts ago.

    ``evidence_count`` rides alongside because the two answer different questions, and a learner
    reading their own meter is owed the same distinction the director gets: a belief resting on one
    answer is not the same as one resting on five.
    """

    node_id: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    recall: float = Field(ge=0.0, le=1.0)
    evidence_count: int = Field(ge=0)
    #: Where the concept stood when the session opened (P2c T5), so the meter reads as movement:
    #: ``None`` for a concept first met today, and on every meter stored before this existed.
    recall_before: float | None = Field(default=None, ge=0.0, le=1.0)


class MasteryMeter(LiveModel):
    """What the learner demonstrated, shown when the session ends.

    Only concepts with evidence appear. A meter listing every concept on the map at zero would read
    as a report card for a course nobody enrolled in, and it would bury the part that is theirs.
    """

    kind: Literal[SurfaceKind.MASTERY_METER] = SurfaceKind.MASTERY_METER
    #: In the map's own teaching order, so two sittings on one map tell the same story.
    entries: list[MeterEntry] = Field(default_factory=list)
