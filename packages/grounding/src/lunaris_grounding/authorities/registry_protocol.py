from typing import Protocol

from lunaris_grounding.authorities.scholarly_record import ScholarlyRecord


class IScholarlyRegistry(Protocol):
    """Resolves a source to its peer-reviewed record, if any (P6.2 §4a, registry layer).

    One integration that spans every discipline (chosen: OpenAlex, P6.3) so authority scales without
    a per-field allowlist. Injected into the credibility scorer; a resolved record floors the
    source's tier at REPUTABLE. Best-effort + off the critical path — ``lookup`` returns None for an
    unknown or on any failure, so grounding degrades to the tier prior, not breaks. Live lookup is
    P6.3; the stub returns None for everything (no-key, offline).
    """

    async def lookup(self, url: str) -> ScholarlyRecord | None: ...
