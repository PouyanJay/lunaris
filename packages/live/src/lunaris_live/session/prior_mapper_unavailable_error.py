class PriorMapperUnavailableError(RuntimeError):
    """The prior mapper could not place the learner: the provider was down, timed out, or answered
    with something no placement can be read from.

    Degraded, never fatal: a placement with no priors is a session taught from the root, which is
    exactly what every session was before the interview existed. The interview's answers are still
    on the row; a later build can map them again.
    """
