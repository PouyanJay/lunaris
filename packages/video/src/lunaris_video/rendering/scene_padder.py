import asyncio
from pathlib import Path

import structlog

from lunaris_video.rendering.sandbox import run_sandboxed

_logger = structlog.get_logger(__name__)

_FFMPEG_PAD_TIMEOUT_S = 60.0


async def pad_scene_tail(mp4_path: Path, extra_s: float) -> bool:
    """Freeze the last frame of a (video-only) scene MP4 for ``extra_s`` more seconds, in place.

    Gate 1 (the length gate, C3) uses this to stretch a slightly-short render up to its audio window
    — a held closing frame — instead of shipping the gap as a narration desync. ``tpad`` re-encodes
    with the same ``libx264`` / ``yuv420p`` profile the scene renders use, so the padded scene still
    stream-copy concatenates with the others (verified: the assembler concats with ``-c copy``).

    Best-effort: returns ``True`` when the pad succeeded (the original is replaced in place), or
    ``False`` on any ffmpeg failure — the caller then keeps the original and records the residual
    drift, so a pad failure degrades rather than failing the job. Sandboxed: the MP4 is untrusted.
    """
    if extra_s <= 0:
        return False
    padded = mp4_path.with_name(f"{mp4_path.stem}.padded.mp4")
    argv = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        mp4_path.name,
        "-vf",
        f"tpad=stop_mode=clone:stop_duration={extra_s:.3f}",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        padded.name,
    ]
    result = await run_sandboxed(argv, cwd=mp4_path.parent, timeout_s=_FFMPEG_PAD_TIMEOUT_S)
    if not result.succeeded or not await asyncio.to_thread(padded.is_file):
        _logger.warning("scene_padder.pad_failed", scene=mp4_path.name, stderr=result.stderr_tail)
        return False
    await asyncio.to_thread(padded.replace, mp4_path)
    return True
