from dataclasses import dataclass


@dataclass(frozen=True)
class GroundedClaim:
    """One verifier-PASSED claim a video may assert, ready for the PLAN prompt and Gate C.

    The runtime ``Claim`` carries no id of its own, so the packet builder synthesizes a stable
    ``id`` (``c1``, ``c2``, …) the planner cites and provenance records. ``text`` is the exact
    verified sentence Gate C diffs scene figures against; ``citation_id`` is the ``supported_by``
    pointer into the course's ``provenance``, and ``source_label`` is the human name the planner
    shows so it knows where a fact comes from.
    """

    id: str
    text: str
    citation_id: str
    source_label: str
