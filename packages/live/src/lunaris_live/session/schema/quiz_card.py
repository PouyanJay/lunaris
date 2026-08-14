from typing import Literal

from pydantic import Field

from ...graph.schema.base import LiveModel
from .surface_kind import SurfaceKind


class QuizCard(LiveModel):
    """The concept's authored misconceptions, with the truth among them.

    Built entirely from what Phase 1 already wrote: the compiler pays a model call per concept to
    author misconceptions *"as the learner would believe them"*, and this is the moment that
    investment pays. Nothing here is generated at render time, which is what keeps a component that
    feeds the learner model deterministic (plan §8).

    **The correct option is deliberately absent from this payload.** The learner's choice comes back
    as their answer and is graded where every other answer is — by the separate grader, against the
    criterion the turn staged (U1). Marking it in the browser would be a second assessment path with
    a different meaning, and the belief would move on whichever one happened to run.
    """

    kind: Literal[SurfaceKind.QUIZ_CARD] = SurfaceKind.QUIZ_CARD
    node_id: str = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=500)
    #: In a stable order that is not the order they were authored in — see ``select_surface``.
    options: list[str] = Field(min_length=2)
