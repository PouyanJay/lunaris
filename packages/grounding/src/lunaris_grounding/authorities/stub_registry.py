from lunaris_grounding.authorities.scholarly_record import ScholarlyRecord


class StubScholarlyRegistry:
    """A no-op scholarly registry — the no-key / offline default (P6.2).

    Resolves nothing, so the credibility scorer falls back to the tier prior alone. The real
    OpenAlex-backed registry (P6.3) replaces it once auto-discovery feeds web sources that need
    peer-reviewed corroboration.
    """

    async def lookup(self, url: str) -> ScholarlyRecord | None:
        return None
