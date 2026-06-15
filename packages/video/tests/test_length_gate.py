"""Gate 1 (length gate) tests: a scene's rendered video must be as long as its audio timeline —
``total_s`` (the sum of its beat windows) plus the SCENE_CLOSE_FADE_S closing fade — within a few
frames. ``evaluate`` returns the drift in seconds when it exceeds tolerance (else None); it never
raises — the pipeline records the drift and ships the video best-effort. Deterministic (one ffprobe,
no model call): a stub probe stands in for the real measurement so the arithmetic + tolerance are
the SUT."""

from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from lunaris_video.assembly import SCENE_CLOSE_FADE_S
from lunaris_video.gates import LengthGate
from lunaris_video.gates.length_gate import _TOLERANCE_S

_TOTAL_S = 6.2  # an arbitrary scene timeline; the closing fade is added on top


def _probe(value: float) -> Callable[[Path], Awaitable[float]]:
    async def probe(mp4_path: Path) -> float:
        return value

    return probe


def _gate(actual: float) -> LengthGate:
    return LengthGate(probe=_probe(actual))


async def test_a_scene_that_matches_its_timeline_reports_no_drift(tmp_path: Path) -> None:
    # actual == total_s + the closing fade → no drift.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S)
    assert await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S) is None


async def test_a_scene_within_a_frame_of_its_timeline_reports_no_drift(tmp_path: Path) -> None:
    # ~one 30fps frame (0.017s) off is pure quantization — well inside tolerance.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S + 0.017)
    assert await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S) is None


async def test_drift_just_within_tolerance_reports_no_drift(tmp_path: Path) -> None:
    # Just inside the tolerance boundary — None (pins the threshold from below).
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S + _TOLERANCE_S - 0.001)
    assert await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S) is None


async def test_drift_just_beyond_tolerance_is_reported(tmp_path: Path) -> None:
    # Just outside the tolerance boundary — a non-None drift (pins the threshold from above).
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S + _TOLERANCE_S + 0.001)
    assert await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S) is not None


async def test_a_scene_longer_than_its_timeline_reports_the_positive_drift(tmp_path: Path) -> None:
    # 0.8s long: a beat's animations overran their window, so the narration lags the visuals.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S + 0.8)
    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)
    assert drift == pytest.approx(0.8, abs=0.01)  # the actual drift, not just its sign


async def test_a_scene_shorter_than_its_timeline_reports_the_negative_drift(tmp_path: Path) -> None:
    # 0.7s short: the closing fade is missing, so every later scene would start early (drift).
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S - 0.7)
    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)
    assert drift == pytest.approx(-0.7, abs=0.01)  # the actual drift, not just its sign
