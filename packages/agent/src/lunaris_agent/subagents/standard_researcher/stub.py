from lunaris_runtime.schema import CourseBrief, StandardResearch


class StubStandardResearcher:
    """Returns preconfigured research findings. Lets the pipeline run without a search key.

    Defaults to ``StandardResearch()`` (``status=UNAVAILABLE``, no sources) — the honest no-key
    outcome the composition root wires when ``SEARCH_API_KEY`` is unset, so the no-key CI path
    skips research deterministically. Tests inject grounded findings to drive the later stages.
    """

    def __init__(self, research: StandardResearch | None = None) -> None:
        self._research = research or StandardResearch()

    async def research(self, brief: CourseBrief) -> StandardResearch:
        return self._research
