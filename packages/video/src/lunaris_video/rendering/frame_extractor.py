import asyncio
from pathlib import Path

import structlog

from lunaris_video.errors import SceneFrameExtractionError
from lunaris_video.rendering.sandbox import run_sandboxed

_logger = structlog.get_logger(__name__)

# The skill's QA sampling: defects appear and disappear as a scene animates, so one frame is
# never enough — sample early/middle/late (a validated defect was only visible late in its scene).
_SAMPLE_FRACTIONS = (0.30, 0.60, 0.90)
_FFPROBE_TIMEOUT_S = 30.0
_FFMPEG_TIMEOUT_S = 60.0


class FrameExtractor:
    """Extracts the 30/60/90% frames of a scene MP4 as PNG bytes — Gate B's eyes.

    ffprobe/ffmpeg run through the same hardened sandbox as the render (the MP4 is the output of
    untrusted generated code): minimal env, timeout, bounded output. Frames are written into the
    MP4's own directory and read back as bytes so the gate can hand them straight to the vision
    model.
    """

    async def extract(self, mp4_path: Path) -> list[bytes]:
        duration = await self._probe_duration(mp4_path)
        frames: list[bytes] = []
        for fraction in _SAMPLE_FRACTIONS:
            frame_path = mp4_path.with_name(f"{mp4_path.stem}_qa_{int(fraction * 100)}.png")
            await self._extract_one(mp4_path, frame_path, timestamp=duration * fraction)
            frames.append(await asyncio.to_thread(frame_path.read_bytes))
        _logger.info("frame_extractor.extracted", scene=mp4_path.stem, frames=len(frames))
        return frames

    async def extract_at(self, mp4_path: Path, at_seconds: float) -> bytes:
        """The single frame at ``at_seconds`` on the timeline — Gate D's per-beat midpoint sample.

        Returned as image bytes for the vision seam. (Internally the frame is written beside the MP4
        with a millisecond-keyed name so concurrent per-beat extractions never collide.)
        """
        frame_path = mp4_path.with_name(f"{mp4_path.stem}_sync_{int(at_seconds * 1000)}.png")
        await self._extract_one(mp4_path, frame_path, timestamp=at_seconds)
        return await asyncio.to_thread(frame_path.read_bytes)

    async def _probe_duration(self, mp4_path: Path) -> float:
        argv = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            mp4_path.name,
        ]
        result = await run_sandboxed(argv, cwd=mp4_path.parent, timeout_s=_FFPROBE_TIMEOUT_S)
        if not result.succeeded:
            raise SceneFrameExtractionError(
                f"ffprobe failed on {mp4_path.name}: {result.stderr_tail}"
            )
        try:
            return float(result.stdout_tail.strip())
        except ValueError as exc:
            raise SceneFrameExtractionError(
                f"ffprobe returned no duration for {mp4_path.name}"
            ) from exc

    async def _extract_one(self, mp4_path: Path, frame_path: Path, *, timestamp: float) -> None:
        argv = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            mp4_path.name,
            "-frames:v",
            "1",
            frame_path.name,
        ]
        result = await run_sandboxed(argv, cwd=mp4_path.parent, timeout_s=_FFMPEG_TIMEOUT_S)
        wrote_frame = await asyncio.to_thread(frame_path.is_file)
        if not result.succeeded or not wrote_frame:
            raise SceneFrameExtractionError(f"ffmpeg failed to extract a frame at {timestamp:.3f}s")
