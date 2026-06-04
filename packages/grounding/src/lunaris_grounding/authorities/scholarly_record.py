from dataclasses import dataclass


@dataclass(frozen=True)
class ScholarlyRecord:
    """A source's peer-reviewed record, resolved from a scholarly registry (P6.2 registry layer).

    The lever that scales authority across every academic field without a per-field list: "is this a
    real, cited, peer-reviewed paper, and in what venue" answered against one registry. ``venue`` is
    the journal/conference; ``doi`` and ``citation_count`` are optional corroboration. A resolved
    record floors a source's tier at REPUTABLE — an unknown domain hosting a real paper is not open
    web. The live OpenAlex-backed lookup is P6.3; here only the seam + a stub exist.
    """

    venue: str | None = None
    doi: str | None = None
    citation_count: int | None = None
