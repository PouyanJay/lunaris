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
from lunaris_video.gates.length_gate import _MAX_PAD_S, _TOLERANCE_S

_TOTAL_S = 6.2  # an arbitrary scene timeline; the closing fade is added on top


def _probe(value: float) -> Callable[[Path], Awaitable[float]]:
    async def probe(mp4_path: Path) -> float:
        return value

    return probe


def _gate(actual: float) -> LengthGate:
    return LengthGate(probe=_probe(actual))


class _SeqProbe:
    """A probe that returns scripted durations in order (repeating the last): the first reading is
    the raw render; the second models the re-measure after a pad fired."""

    def __init__(self, values: list[float]) -> None:
        self.values = values
        self.calls = 0

    async def __call__(self, mp4_path: Path) -> float:
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


class _FakePadder:
    """Records the seconds it was asked to pad; ``ok`` models whether ffmpeg succeeded."""

    def __init__(self, *, ok: bool = True) -> None:
        self.calls: list[float] = []
        self._ok = ok

    async def __call__(self, mp4_path: Path, extra_s: float) -> bool:
        self.calls.append(extra_s)
        return self._ok


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
    # 0.7s short, NO padder wired: the closing fade is missing, so every later scene would start
    # early (drift) — recorded as before when auto-pad is unavailable.
    gate = _gate(_TOTAL_S + SCENE_CLOSE_FADE_S - 0.7)
    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)
    assert drift == pytest.approx(-0.7, abs=0.01)  # the actual drift, not just its sign


async def test_a_short_scene_is_padded_to_its_window(tmp_path: Path) -> None:
    # C3 — 0.7s short with a padder wired: the gate pads the missing tail and re-measures to a
    # match, so a small short drift no longer ships as a desync.
    expected = _TOTAL_S + SCENE_CLOSE_FADE_S
    probe = _SeqProbe([expected - 0.7, expected])  # short, then exact after the pad
    padder = _FakePadder()
    gate = LengthGate(probe=probe, pad=padder)

    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)

    assert drift is None  # padded up to its window
    assert padder.calls == pytest.approx([0.7], abs=0.01)  # padded by exactly the missing seconds
    assert probe.calls == 2  # measured, padded, re-measured


async def test_a_padded_scene_with_residual_drift_still_reports_it(tmp_path: Path) -> None:
    # The pad fired but the re-measure is still short (a partial pad): the residual drift is kept.
    expected = _TOTAL_S + SCENE_CLOSE_FADE_S
    probe = _SeqProbe([expected - 1.0, expected - 0.3])  # 1.0s short, padded but 0.3s still short
    gate = LengthGate(probe=probe, pad=_FakePadder())

    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)

    assert drift == pytest.approx(-0.3, abs=0.01)


async def test_a_short_scene_whose_pad_fails_reports_the_drift(tmp_path: Path) -> None:
    # ffmpeg pad failed (returns False): the gate keeps the original render and records the drift —
    # a pad failure degrades, it never fails the job.
    expected = _TOTAL_S + SCENE_CLOSE_FADE_S
    padder = _FakePadder(ok=False)
    gate = LengthGate(probe=_probe(expected - 0.7), pad=padder)

    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)

    assert drift == pytest.approx(-0.7, abs=0.01)
    assert padder.calls == pytest.approx([0.7], abs=0.01)  # the pad was attempted


async def test_a_short_scene_beyond_the_pad_band_is_not_padded(tmp_path: Path) -> None:
    # Too short to be quantization or a missing fade (a whole beat under-ran): record it, never
    # paper over a real authoring problem with a multi-second frozen frame.
    too_short = _MAX_PAD_S + 0.5
    padder = _FakePadder()
    gate = LengthGate(probe=_probe(_TOTAL_S + SCENE_CLOSE_FADE_S - too_short), pad=padder)

    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)

    assert drift == pytest.approx(-too_short, abs=0.01)
    assert padder.calls == []  # never attempted


async def test_a_long_scene_is_never_padded(tmp_path: Path) -> None:
    # A long render cannot be trimmed without cutting the closing fade, so padding does not apply —
    # the positive drift is recorded.
    padder = _FakePadder()
    gate = LengthGate(probe=_probe(_TOTAL_S + SCENE_CLOSE_FADE_S + 0.8), pad=padder)

    drift = await gate.evaluate("S1_x", tmp_path / "S1X.mp4", _TOTAL_S)

    assert drift == pytest.approx(0.8, abs=0.01)
    assert padder.calls == []  # only short scenes are paddable
