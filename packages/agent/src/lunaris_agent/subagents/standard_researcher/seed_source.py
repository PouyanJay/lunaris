from dataclasses import dataclass

from lunaris_runtime.schema import TrustTier


@dataclass(frozen=True)
class SeedSource:
    """A page the research stage already fetched + extracted, ready to seed the grounding corpus.

    The research stage (P7.2) searches authoritative sources, fetches + extracts their full text,
    and distils competencies — then discards the text once the provenance (``ResearchSource``) is
    built. ``SeedSource`` carries that already-paid-for text forward so the SEED feed (P6.4) can
    ingest it into the per-course corpus without re-fetching: the build grounds claims against the
    very pages it read to design the course.

    A transient domain value inside the harness — it never crosses the wire (the reader-facing
    ``ResearchSource`` stays text-free). ``trust_tier`` is the tier classified at search time; the
    credibility is intentionally left to the ingestor's scorer, so a seed is graded by the same gate
    as every other source (seeded is not the same as trusted).
    """

    url: str
    text: str
    title: str | None = None
    trust_tier: TrustTier | None = None
    fetched_at: str | None = None
