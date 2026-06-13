from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenderedScene:
    """A scene that cleared Gate A: its MP4 on disk and the source that produced it.

    The source travels with the artifact because Gate B's targeted repairs edit and re-render
    EXACTLY this code — never a regeneration from the contract.
    """

    scene_id: str
    mp4_path: Path
    source: str
