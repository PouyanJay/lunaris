"""Real-ffmpeg test for ``pad_scene_tail`` (C3): freezing a short scene's last frame up to its
audio window. Self-skips when ffmpeg/ffprobe are absent (CI without the render extra); it needs no
manim — a synthetic ``testsrc`` clip stands in for a render. Proves the actual tpad op extends the
video to the target length, the hermetic ``test_length_gate`` covers the gate logic around it."""

import shutil
from pathlib import Path

import pytest
from lunaris_video.rendering import pad_scene_tail, probe_scene_duration, run_sandboxed

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="needs ffmpeg + ffprobe (the render extra)",
)


async def _testsrc(mp4_path: Path, *, seconds: float) -> None:
    # A real video-only h264/yuv420p clip — the shape a manim render produces, so the pad path is
    # exercised end to end without manim.
    argv = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={seconds}:size=320x240:rate=30",
        "-pix_fmt",
        "yuv420p",
        "-c:v",
        "libx264",
        mp4_path.name,
    ]
    result = await run_sandboxed(argv, cwd=mp4_path.parent, timeout_s=60.0)
    assert result.succeeded, result.stderr_tail


async def test_pad_scene_tail_extends_a_short_render_to_its_window(tmp_path: Path) -> None:
    # Arrange — a 1.0s clip that needs to reach 1.5s (0.5s short).
    mp4 = tmp_path / "S1Hook.mp4"
    await _testsrc(mp4, seconds=1.0)
    assert await probe_scene_duration(mp4) == pytest.approx(1.0, abs=0.05)

    # Act — freeze the last frame for the missing 0.5s, in place.
    padded = await pad_scene_tail(mp4, 0.5)

    # Assert — it padded, and the video is now ~1.5s.
    assert padded is True
    assert await probe_scene_duration(mp4) == pytest.approx(1.5, abs=0.05)


async def test_pad_scene_tail_is_a_noop_for_a_non_positive_amount(tmp_path: Path) -> None:
    # A long/exact scene is never padded — the gate only calls this for a positive missing amount,
    # but the guard makes the contract explicit.
    mp4 = tmp_path / "S1Hook.mp4"
    await _testsrc(mp4, seconds=1.0)

    assert await pad_scene_tail(mp4, 0.0) is False
    assert await probe_scene_duration(mp4) == pytest.approx(1.0, abs=0.05)
