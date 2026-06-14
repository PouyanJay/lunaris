from pathlib import Path
from typing import Protocol

from lunaris_video.models import RenderedScene, RenderedVideo
from lunaris_video.schemas import TimingManifest, VideoContract


class IVideoAssembler(Protocol):
    """Stage 4 seam: cleared per-scene MP4s + contract + the timing manifest → the artifact bundle.

    ``manifest`` is the SAME manifest that drove the render (audio-drives-video): the assembler
    persists it as ``timing.json`` rather than re-deriving it, so the manifest the scene code was
    built against and the one shipped to the player are guaranteed identical. ``audio_dir`` holds
    the per-beat clips a voiced manifest references — required when the manifest is voiced (the
    assembler mixes + muxes them and emits WebVTT captions), ignored for a silent one.
    """

    async def assemble(
        self,
        scenes: list[RenderedScene],
        contract: VideoContract,
        *,
        manifest: TimingManifest,
        workdir: Path,
        audio_dir: Path | None = None,
    ) -> RenderedVideo: ...
