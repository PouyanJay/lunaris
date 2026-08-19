from pydantic import Field

from ...graph.schema.base import LiveModel
from .move_kind import MoveKind


class DirectorMove(LiveModel):
    """One decision by the director, with the reasoning that produced it.

    ``reason`` is not decoration. Plan §7: "the director emits its reasoning into the session trace
    so every move is auditable" — a session is dozens of choices made in seconds on a learner's
    behalf, and the only way to tell a good policy from a lucky one afterwards is to read why each
    choice was made. It is written for a human reading a transcript, not for a parser.
    """

    kind: MoveKind
    #: The concept this move is about; ``None`` only for ``CLOSE`` (about the session) and ``PLACE``
    #: (about the learner, before there are concepts).
    node_id: str | None = None
    reason: str = Field(min_length=1, max_length=500)
