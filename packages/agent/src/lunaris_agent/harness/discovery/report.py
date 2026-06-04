"""The outcome of one discovery run, returned by :class:`IGroundingDiscoverer`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryReport:
    """What a discovery pass ingested into the per-course corpus.

    Transient working state inside the harness (never crosses the wire) — the ``discover_grounding``
    tool reads it to report a source count to the agent, and the canvas already saw the per-source
    detail via the streamed ``SOURCE_EVALUATED`` events. ``covered_kcs`` records which KCs ended the
    pass with accepted evidence, so the reflect loop (P6.3-T3) knows what is still uncovered.
    """

    chunks_ingested: int = 0
    sources_accepted: int = 0
    covered_kcs: tuple[str, ...] = ()
