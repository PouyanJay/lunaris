import hashlib

from .constants import SUPPORTED_DIAGRAM_PREFIXES
from .render_result import RenderResult


class StubDiagramRenderer:
    """Deterministic renderer for tests — validates syntactically, no sandbox.

    Treats source opening with a recognised diagram type as a successful render (returning a
    stable fake path); anything else fails. Pass ``fail_on`` to force a failure when the
    source contains a marker, to exercise the engine's repair/skip path.
    """

    def __init__(self, *, fail_on: str | None = None) -> None:
        self._fail_on = fail_on

    async def render(self, source: str) -> RenderResult:
        if self._fail_on is not None and self._fail_on in source:
            return RenderResult(ok=False, error="stub: forced failure")
        if not source.strip().startswith(SUPPORTED_DIAGRAM_PREFIXES):
            return RenderResult(ok=False, error="stub: unrecognised diagram type")
        digest = hashlib.sha256(source.encode()).hexdigest()[:16]
        return RenderResult(ok=True, path=f"visuals/{digest}.svg")
