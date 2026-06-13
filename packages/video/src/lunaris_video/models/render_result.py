from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderResult:
    """One scene-render attempt's outcome: the MP4 when it worked, the trace tail when not."""

    succeeded: bool
    mp4_path: Path | None
    error_tail: str
