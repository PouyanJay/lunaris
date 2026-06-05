from dataclasses import dataclass, field

from lunaris_runtime.schema import StandardResearch

from .seed_source import SeedSource


@dataclass(frozen=True)
class ResearchOutcome:
    """What the research stage produced: the reader-facing findings + the corpus seed material.

    ``research`` is the ``StandardResearch`` recorded on the brief and rendered to the learner (its
    competencies, score table, and provenance) — the unchanged P7.2 contract. ``seeds`` is the
    transient, harness-only carry of the pages the stage already fetched + extracted, so the SEED
    feed (P6.4) can ingest them into the corpus without re-fetching. Keeping the two together lets a
    single ``research()`` call serve both the brief and the corpus, with the full text never leaking
    onto the wire (it rides ``seeds``, not ``research``).

    A frozen value object — a tightly-coupled sibling of ``SeedSource`` (its companion return type).
    ``seeds`` is empty exactly when the stage fetched nothing (the honest UNAVAILABLE outcome).
    """

    research: StandardResearch
    seeds: tuple[SeedSource, ...] = field(default_factory=tuple)
