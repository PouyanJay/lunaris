from enum import StrEnum


class LayoutComponent(StrEnum):
    """The allow-list. Every component a Tier 2 layout may name, and there is no other way in.

    R6: the tutor composes from a fixed catalog of our own tokenized components, never free-form
    markup and never an arbitrary A2UI primitive. Plan §8 permits generative composition and
    ``enterprise-ui`` forbids one-off components, and an allow-list is the only reading that
    satisfies both.

    The values are the names that travel on the wire and the keys the browser's renderer switches
    on, so they are written the way a component is rather than the way an enum member is.

    Two of them carry no content of their own. ``PROSE`` and ``SURFACE`` are **slots**: the tutor's
    words and the director's Tier 1 card already live on the turn, and a layout carrying a second
    copy of either would be free to disagree with the thing the learner is actually marked on.
    """

    STACK = "Stack"
    PROSE = "Prose"
    SURFACE = "Surface"
    WORKED_EXAMPLE = "WorkedExample"
    HINT = "Hint"
    PRACTICE = "Practice"
