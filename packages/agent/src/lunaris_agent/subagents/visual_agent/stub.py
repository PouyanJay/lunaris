from collections.abc import Callable

from .draft import VisualDraft


class StubVisualGenerator:
    """Deterministic generator for tests — a configurable function of the concept.

    The default emits a simple two-node flowchart for every concept; pass ``fn`` to return
    ``None`` (no diagram) or bespoke Mermaid for specific concepts.
    """

    def __init__(self, fn: Callable[[str, str], VisualDraft | None] | None = None) -> None:
        self._fn = fn or (
            lambda concept, _context: VisualDraft(f'graph TD\n  A["{concept}"] --> B["apply it"]')
        )

    async def generate(self, concept: str, context: str) -> VisualDraft | None:
        return self._fn(concept, context)
