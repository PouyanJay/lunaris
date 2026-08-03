from pydantic import Field

from .base import LiveModel


class GraphEdit(LiveModel):
    """One entry in a graph's append-only history: what a learner's question added, and why.

    A compiled map is a claim about a subject; an extended one is a claim plus a record of how it
    came to differ. Without that record, a graph that grew during a session is indistinguishable
    from one the compiler produced badly — and the first question anyone asks about a strange map
    is which of those it is.

    Ordered by ``version``: the log is append-only and the version is monotonic, so the sequence is
    the history. No timestamp — nothing yet reads one, and a clock in this contract would be a
    source of nondeterminism in every test that touches it. Phase 2 adds the session and turn that
    asked, once those exist to be named.
    """

    #: The graph version this edit produced. Version 1 is the cold compile and has no edit.
    version: int = Field(ge=2)
    #: The learner's request, in their words — the "why" this concept is on the map at all.
    request: str = Field(min_length=1, max_length=500)
    #: Ids of the concepts this edit added.
    added: list[str] = Field(default_factory=list)
    #: Ids of the existing concepts the new material was hung from.
    anchors: list[str] = Field(default_factory=list)
