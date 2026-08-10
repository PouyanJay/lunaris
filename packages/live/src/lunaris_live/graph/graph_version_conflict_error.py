from lunaris_runtime.persistence import PersistenceError


class GraphVersionConflictError(PersistenceError):
    """Someone else moved the graph on while this extension was being built.

    A cold compile writes a graph once. An extension read a version, spent seconds thinking, and
    now wants to write the next one — and in a session two turns can overlap, or a request can be
    retried. A blind write would let the later one silently discard the earlier one's concepts,
    which a learner experiences as a question they asked simply never landing.

    So the write is conditional on the version it read, and this is what losing that race looks
    like: recoverable by re-reading and re-applying, never by pretending it did not happen.

    Subclasses ``PersistenceError`` deliberately. The stores wrap their bodies in ``guard``, which
    translates any other exception into a generic ``PersistenceError`` — a conflict raised as
    anything else would be flattened into "the database broke" and lose the one thing that makes it
    actionable.
    """
