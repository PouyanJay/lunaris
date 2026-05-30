# Mermaid diagram types this MVP supports. Shared by the parser (what to accept from the
# generator) and the stub renderer (what counts as a valid diagram) so they never drift.
SUPPORTED_DIAGRAM_PREFIXES: tuple[str, ...] = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "stateDiagram",
    "classDiagram",
    "erDiagram",
)
