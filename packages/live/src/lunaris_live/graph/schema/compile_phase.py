from enum import StrEnum


class CompilePhase(StrEnum):
    """Which part of a cold compile is happening.

    The phases are named for what the *learner* is waiting on rather than for the code that runs
    them, because this is the one enum whose values reach a screen. They also fail differently and
    at different scales — decomposition is one call, authoring is one per concept — so a stalled
    compile is diagnosable from the last phase reported.
    """

    #: One serial call: nothing is countable yet, because the concepts are not known.
    DECOMPOSING = "decomposing"
    #: One call per concept, concurrent — the long phase, and the only countable one.
    AUTHORING = "authoring"
    #: Deriving order and acyclicity from the finished concepts. Fast, but not free.
    ASSEMBLING = "assembling"
