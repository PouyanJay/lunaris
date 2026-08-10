class SessionClosedError(RuntimeError):
    """The session has already ended, so it cannot take another turn.

    Reachable from an ordinary stale tab: the director closes a session, and a learner who left the
    page open answers into it a minute later. Refusing is not pedantry — reopening it would let a
    session run past the bound the director just enforced, and the close is the one decision the
    whole clock exists to make.
    """
