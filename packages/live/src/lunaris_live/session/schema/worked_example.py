from pydantic import Field

from ...graph.schema.base import LiveModel


class WorkedExample(LiveModel):
    """One example worked through in steps, as the tutor wrote it.

    Steps rather than a paragraph, because the layout has to be able to show it collapsed: a
    disclosure needs a title to show and a body to hide, and a wall of prose gives it neither.
    """

    title: str = Field(min_length=1, max_length=200)
    #: Ordered. Bounded because a worked example that runs to fifteen steps is a lesson, and the
    #: turn already has one of those.
    steps: list[str] = Field(min_length=1, max_length=6)
