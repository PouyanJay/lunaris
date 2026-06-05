"""The outcome of one seed pass, returned by :class:`IGroundingSeeder`."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedReport:
    """What a seed pass ingested into the per-course corpus from the research stage fetches (P6.4).

    Transient working state inside the harness (never crosses the wire) — the ``seed_grounding``
    tool reads it to report a source count to the agent and to drive the live "seeded N sources"
    canvas beat. ``sources_seeded`` counts the research pages turned into corpus sources;
    ``chunks_ingested`` the resulting chunks (a source yields several).
    """

    sources_seeded: int = 0
    chunks_ingested: int = 0
