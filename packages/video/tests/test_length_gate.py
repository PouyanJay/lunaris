"""Gate 1 (length gate) tests: a scene's rendered video must be as long as its audio timeline —
``total_s`` (the sum of its beat windows) plus the SCENE_CLOSE_FADE_S closing fade — within a few
frames, or the narration drifts against the visuals. Deterministic (one ffprobe, no model call): a
stub probe stands in for the real measurement so the gate's arithmetic + tolerance are the SUT."""

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from lunaris_video.assembly import SCENE_CLOSE_FADE_S
from lunaris_video.errors import TimingGateError
from lunaris_video.gates import LengthGate

_TOTAL_S = 6.2  # an arbitrary scene timeline; the closing fade is added on top


def _probe(value: float) -> Callable[[Path], Awaitable[float]]:
    async def probe(mp4_path: Path) -> float:
        return value

    return probe


def _gate(actual: float) -> LengthGate:
    return LengthGate(probe=_probe(actual))


async def test_a_scene_that_matches_its_timeline_passes(tmp_path: Path) -> None:
    # actual == total_s + the closing fade → no drift, no raise.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S)
    await gate.check("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)


async def test_a_scene_within_a_frame_of_its_timeline_passes(tmp_path: Path) -> None:
    # ~one 30fps frame (0.017s) off is pure quantization — well inside tolerance, no raise.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S + 0.017)
    await gate.check("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)


async def test_a_scene_longer_than_its_timeline_fails(tmp_path: Path) -> None:
    # 0.8s long: a beat's animations overran their window, so the narration would lag the visuals.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S + 0.8)

    with pytest.raises(TimingGateError) as excinfo:
        await gate.check("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)
    assert excinfo.value.scene_id == "S1_x"
    assert excinfo.value.actual > excinfo.value.expected


async def test_a_scene_shorter_than_its_timeline_fails(tmp_path: Path) -> None:
    # 0.7s short: the closing fade is missing, so every later scene would start early (drift).
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S - 0.7)

    with pytest.raises(TimingGateError) as excinfo:
        await gate.check("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)
    assert excinfo.value.actual < excinfo.value.expected
