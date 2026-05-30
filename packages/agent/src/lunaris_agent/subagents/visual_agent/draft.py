from dataclasses import dataclass


@dataclass(frozen=True)
class VisualDraft:
    """A proposed diagram for a concept: Mermaid diagram-as-code, before it is rendered."""

    source: str
