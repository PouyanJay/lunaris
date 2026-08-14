from enum import StrEnum


class TurnBeat(StrEnum):
    """What one item of a turn's stream is.

    The discriminant of the ``(beat, payload)`` pairs the session plane yields to its AG-UI
    translator. A ``StrEnum`` rather than the bare strings Phase 1's compile stream uses, because
    T3 through T5 add producers to this same stream (Tier 1 specs, A2UI layouts) and every one of
    them is a new chance for a typo to become a payload that is silently dropped instead of a name
    that does not exist.

    ``StrEnum`` specifically, so the values still read as themselves in a log line or a traceback —
    which is most of why the string version was pleasant to debug.
    """

    #: A fragment of what the tutor is saying, as it is written.
    DELTA = "delta"
    #: The session the turn produced. Terminal, and exactly one per stream.
    SESSION = "session"
