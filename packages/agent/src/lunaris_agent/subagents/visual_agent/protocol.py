from typing import Protocol

from .draft import VisualDraft


class IVisualGenerator(Protocol):
    """Decides whether a concept warrants a diagram and, if so, produces Mermaid for it.

    Returns ``None`` when no diagram would help (coherence: don't ship decorative visuals).
    Folding the classify step into the generator keeps "should there be a diagram?" and
    "what is it?" as one decision.
    """

    async def generate(self, concept: str, context: str) -> VisualDraft | None: ...
