from collections.abc import Sequence
from typing import Protocol

from ..schema import InterviewExchange


class IInterviewer(Protocol):
    """Runs the placement conversation while the map compiles (plan §6, P2c).

    Split from ``ITutor`` rather than added to it: the tutor's methods all take a director's move
    on a concept, and the interview has neither — it happens *before* there is a map for a director
    to decide over. A protocol of its own also keeps the offline path honest, because the stub
    interviewer has to be able to carry a whole session in `make run` without a key.

    ``exchanges`` is what has been asked and answered so far, oldest first. ``graph_has_landed``
    says whether the map has arrived: the interview absorbs the compile and never extends it (T2),
    so an interviewer told the map is there is being asked to wrap up. ``run_id`` is the turn's own
    run (R5), not the session's.

    Answers the next question, or ``None`` when it has heard enough — which is the interviewer's
    to say, within the bounds the loop puts on it (T2).
    """

    async def ask(
        self,
        topic: str,
        *,
        exchanges: Sequence[InterviewExchange] = (),
        graph_has_landed: bool = False,
        run_id: str,
    ) -> str | None: ...
