from enum import StrEnum


class NodeProvenance(StrEnum):
    """Where a concept node came from.

    Provenance is structural (CLAUDE.md): when a session teaches something wrong, this says without
    ambiguity whether the cold compile produced the node or a learner's mid-session request did.
    ``EXTENDED`` nodes arrive via ``extend_graph`` (C1) and carry the request that asked for them.
    """

    COMPILED = "compiled"
    EXTENDED = "extended"
