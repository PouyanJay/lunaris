from dataclasses import dataclass


@dataclass(frozen=True)
class RenderResult:
    """Outcome of rendering a diagram: ``ok`` plus the rendered path or a failure reason."""

    ok: bool
    path: str | None = None
    error: str | None = None
