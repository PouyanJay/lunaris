from pathlib import Path

from lunaris_video.errors import SceneFrameExtractionError
from lunaris_video.rendering.sandbox import run_sandboxed

_FFPROBE_TIMEOUT_S = 30.0


async def probe_scene_duration(mp4_path: Path) -> float:
    """The container duration of a rendered scene MP4, in seconds, via sandboxed ffprobe.

    The MP4 is the output of untrusted generated code, so ffprobe runs in the same hardened sandbox
    as the render (minimal env, timeout, bounded output). Raises ``SceneFrameExtractionError`` on a
    probe failure or a non-numeric duration. Shared by the frame extractor (where to sample) and the
    length gate (how long the scene rendered).
    """
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
        raise SceneFrameExtractionError(f"ffprobe failed on {mp4_path.name}: {result.stderr_tail}")
    try:
        return float(result.stdout_tail.strip())
    except ValueError as exc:
        raise SceneFrameExtractionError(
            f"ffprobe returned no duration for {mp4_path.name}"
        ) from exc
