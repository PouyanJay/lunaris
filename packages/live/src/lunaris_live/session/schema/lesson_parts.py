from pydantic import Field

from ...graph.schema.base import LiveModel
from .worked_example import WorkedExample


class LessonParts(LiveModel):
    """The material the tutor offers around a lesson — and everything in it is optional.

    This is where Tier 2's generative freedom lives (U4). The tutor writes the worked example, the
    hint and the practice prompts; ``compose_layout`` decides which of them this learner sees, in
    what order, and open or closed. Splitting it that way is the same line Tier 1 draws one tier up:
    the words are a model's, the arrangement is a rule's, and only the second one feeds anything.

    Every field defaulting to empty is load-bearing rather than lenient. An illustration that
    failed, timed out or was never asked for costs the trimmings and never the turn — the lesson
    and the card are on the turn already, so the layout degrades to prose and the question.
    """

    worked_example: WorkedExample | None = None
    hint: str | None = Field(default=None, min_length=1, max_length=500)
    #: Prompts to think through before answering, most useful first — ``compose_layout`` takes them
    #: from the front when a learner needs fewer.
    practice: list[str] = Field(default_factory=list, max_length=4)
