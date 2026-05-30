import re

from .constants import SUPPORTED_DIAGRAM_PREFIXES
from .draft import VisualDraft

_FENCE_RE = re.compile(r"```(?:mermaid)?\s*(.+?)```", re.DOTALL)


def parse_visual(text: str) -> VisualDraft | None:
    """Extract Mermaid source from a generator response, or ``None`` for "no diagram".

    Tolerant of a ```mermaid fenced block or bare source, and of an explicit ``NONE``.
    Returns ``None`` (skip the diagram, never ship a broken one) unless the source's first
    token is a supported diagram type — matching the *exact* token so a hallucinated
    ``graphQL`` doesn't slip past a ``graph`` prefix check.
    """
    stripped = text.strip()
    if not stripped or stripped.upper().startswith("NONE"):
        return None

    match = _FENCE_RE.search(text)
    source = (match.group(1) if match else text).strip()
    if not _opens_with_supported_diagram(source):
        return None
    return VisualDraft(source=source)


def _opens_with_supported_diagram(source: str) -> bool:
    tokens = source.split()
    if not tokens:
        return False
    first = tokens[0]
    return any(
        first == prefix or first.startswith(f"{prefix}-") for prefix in SUPPORTED_DIAGRAM_PREFIXES
    )
