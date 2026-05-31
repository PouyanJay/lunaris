from dataclasses import dataclass

from lunaris_runtime.schema import VisualSpec


@dataclass(frozen=True)
class VisualDraft:
    """A proposed diagram for a concept.

    ``spec`` is the typed branded specification the web draws (the primary experience); ``source``
    is Mermaid diagram-as-code — the fallback, which must render before it ships. Either may be set.
    """

    source: str
    spec: VisualSpec | None = None
