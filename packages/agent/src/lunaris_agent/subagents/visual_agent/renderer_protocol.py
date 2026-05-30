from typing import Protocol

from .render_result import RenderResult


class IDiagramRenderer(Protocol):
    """Renders Mermaid source in a sandbox, reporting whether it produced a valid diagram.

    Implementations must never raise on bad source — they return ``RenderResult(ok=False)``
    so the engine can repair or skip rather than crash the run.
    """

    async def render(self, source: str) -> RenderResult: ...
