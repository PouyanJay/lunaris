from typing import Protocol


class ITutorDeltaSink(Protocol):
    """Somewhere for a fragment of the tutor's words to go while the turn is still running.

    Synchronous and returning nothing, which is the whole contract: a sink is called from inside a
    turn, and one that could block would let a slow client hold up the teaching it is watching. The
    transport-side implementation is an unbounded queue's ``put_nowait`` — the same shape Phase 1's
    ``ICompileProgressSink`` settled on, for the same reason.

    A sink is a client's connection by another name, so it is allowed to fail: ``relay_delta``
    swallows that, because a learner must never lose a paid-for turn to a closed tab.
    """

    def __call__(self, delta: str) -> None: ...
