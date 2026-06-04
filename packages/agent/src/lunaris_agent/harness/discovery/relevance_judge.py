from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RelevanceVerdict:
    """Whether a fetched source is on-topic for a concept, plus a one-line reason for the canvas."""

    relevant: bool
    reason: str = ""


class IRelevanceJudge(Protocol):
    """Judges whether a fetched source teaches a given concept — the discovery gate's reviewer.

    Kept **blind to the source's trust label** (§3): it sees only the concept and the extracted
    text, never the domain or tier, so its on-topic verdict can't be biased by provenance disclosure
    (the user-facing canvas still shows the tier — a different surface, a different rule). It is the
    terminal-reviewer half of the author≠judge separation: the author never selects its own
    evidence, and discovery never ingests a page just because it ranked well in search.

    Best-effort: an implementation that can't reach its model returns a permissive verdict rather
    than silently dropping evidence — discovery degrades to "ingest + let the verifier floor
    decide", never to "cut everything".
    """

    async def is_relevant(
        self, *, kc_label: str, kc_definition: str, text: str
    ) -> RelevanceVerdict: ...
