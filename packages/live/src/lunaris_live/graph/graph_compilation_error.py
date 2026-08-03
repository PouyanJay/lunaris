class GraphCompilationError(ValueError):
    """A topic could not be turned into a map at all.

    Raised only for the failure that cannot degrade: no usable concepts came back, so there is
    nothing to teach. Partial failures — a concept missing its definition, a spec that would not
    parse — deliberately do not raise; the graph is still worth having without them.

    A ``ValueError`` subclass so callers that only care that the input could not be processed keep
    working, while the API can answer honestly that the failure came from upstream rather than
    returning an empty map as though it were a finished one.
    """
