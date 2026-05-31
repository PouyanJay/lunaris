from .constants import SUPPORTED_DIAGRAM_PREFIXES
from .render_result import RenderResult


class PassthroughDiagramRenderer:
    """The no-toolchain renderer: validate the source syntactically, ship it un-rendered.

    The live ``MermaidRenderer`` shells out to the beautiful-mermaid skill to produce an SVG, but
    that toolchain (a JS runtime + the render script) is optional, gated on
    ``LUNARIS_MERMAID_SCRIPT``. When it is absent this renderer still lets a course carry its
    diagrams: it accepts any source opening with a recognised Mermaid diagram type (rejecting prose
    / malformed blocks, exactly as the real renderers do) and reports ``ok=True`` with ``path=None``
    — no SVG on disk.

    That is safe because the web draws a visual from its branded ``spec`` (primary) or its raw
    ``source`` (the ``MermaidFallback``); it never reads ``Visual.rendered``. So a branded spec
    ships unconditionally and a source-only diagram ships as labelled diagram-as-code rather than
    being dropped. Never raises (the engine relies on that to repair/skip, not crash the run).
    """

    async def render(self, source: str) -> RenderResult:
        if not source.strip().startswith(SUPPORTED_DIAGRAM_PREFIXES):
            return RenderResult(ok=False, error="passthrough: unrecognised diagram type")
        return RenderResult(ok=True, path=None)
