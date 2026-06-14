import asyncio
from pathlib import Path

import structlog

from lunaris_video.assembly.timing_estimator import estimate_timing
from lunaris_video.errors import VideoPipelineError
from lunaris_video.models.rendered_scene import RenderedScene
from lunaris_video.models.rendered_video import RenderedVideo
from lunaris_video.rendering.sandbox import run_sandboxed
from lunaris_video.schemas import VideoContract

_logger = structlog.get_logger(__name__)

_CONCAT_TIMEOUT_S = 120.0
_POSTER_TIMEOUT_S = 60.0


class VideoAssembler:
    """Stage 4: concat the cleared per-scene MP4s into the final video, extract a poster, and
    bundle the regeneration artifacts.

    Concat is a stream-copy (``-c copy``): every scene shares the renderer's encoder settings, so
    the join needs no re-encode (the skill's calibration). The poster is the final video's first
    frame as JPEG (the reader's hero-slot still). ``timing.json`` is the WPM estimate — the video
    is silent now but voice-ready. ffmpeg runs in the hardened sandbox; the scenes are
    untrusted-codegen output.
    """

    async def assemble(
        self, scenes: list[RenderedScene], contract: VideoContract, *, workdir: Path
    ) -> RenderedVideo:
        if not scenes:
            raise VideoPipelineError("cannot assemble a video with no rendered scenes")
        final_mp4 = workdir / "final.mp4"
        poster = workdir / "poster.jpg"
        await self._concat(scenes, final_mp4, workdir=workdir)
        await self._extract_poster(final_mp4, poster)
        mp4_bytes, poster_bytes = await asyncio.gather(
            asyncio.to_thread(final_mp4.read_bytes), asyncio.to_thread(poster.read_bytes)
        )
        timing_json = estimate_timing(contract).model_dump_json(indent=2).encode()
        contracts_json = contract.model_dump_json(indent=2).encode()
        _logger.info("video_assembler.assembled", scenes=len(scenes), mp4_bytes=len(mp4_bytes))
        return RenderedVideo(
            mp4=mp4_bytes,
            poster=poster_bytes,
            contracts_json=contracts_json,
            timing_json=timing_json,
        )

    async def _concat(self, scenes: list[RenderedScene], final_mp4: Path, *, workdir: Path) -> None:
        # The concat demuxer reads a list file of `file '<path>'` lines; -safe 0 allows the
        # absolute per-scene paths (they live under media/, not beside the list).
        concat_list = workdir / "concat.txt"
        lines = "".join(f"file '{scene.mp4_path}'\n" for scene in scenes)
        await asyncio.to_thread(concat_list.write_text, lines, encoding="utf-8")
        argv = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list.name,
            "-c",
            "copy",
            final_mp4.name,
        ]
        result = await run_sandboxed(argv, cwd=workdir, timeout_s=_CONCAT_TIMEOUT_S)
        if not result.succeeded or not await asyncio.to_thread(final_mp4.is_file):
            raise VideoPipelineError(f"ffmpeg concat failed: {result.stderr_tail}")

    async def _extract_poster(self, final_mp4: Path, poster: Path) -> None:
        argv = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            final_mp4.name,
            "-frames:v",
            "1",
            poster.name,
        ]
        result = await run_sandboxed(argv, cwd=final_mp4.parent, timeout_s=_POSTER_TIMEOUT_S)
        if not result.succeeded or not await asyncio.to_thread(poster.is_file):
            raise VideoPipelineError(f"ffmpeg poster extraction failed: {result.stderr_tail}")
