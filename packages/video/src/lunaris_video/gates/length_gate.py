from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from lunaris_video.assembly import SCENE_CLOSE_FADE_S
from lunaris_video.errors import TimingGateError

_logger = structlog.get_logger(__name__)

# How far a scene's render may sit from its timeline before it counts as drift. The render duration
# is frame-quantized (~1/30s) and the beat windows are floats, so a few hundredths of a second of
# slack is pure quantization; a real over-budget beat or a missing closing fade is far larger
# (0.5s+ / 0.7s). This catches the latter without false-positiving on the former.
_TOLERANCE_S = 0.15

# Probes a rendered scene MP4 for its duration in seconds. Injectable so the gate is testable with
# no real render; the composition root wires the sandboxed ffprobe.
DurationProbe = Callable[[Path], Awaitable[float]]


class LengthGate:
    """Gate 1 (deterministic, voiced-only): a scene's rendered video must be as long as its audio
    timeline — ``total_s`` (the sum of its beat windows) plus the ``SCENE_CLOSE_FADE_S`` closing
    fade — within a few frames.

    A mismatch means a beat's animations overran their window, or the closing fade is missing/extra,
    so the narration would drift against the visuals (and the error compounds across scenes). Unlike
    Gate D (the vision sync check), this is a single ``ffprobe`` with no model call, so it runs as a
    cheap pre-check; a miss raises ``TimingGateError``, which the pipeline recovers by delivering a
    silent video — a desynced voiced one is never shipped.
    """

    def __init__(self, *, probe: DurationProbe) -> None:
        self._probe = probe

    async def check(self, scene_id: str, mp4_path: Path, total_s: float) -> None:
        actual = await self._probe(mp4_path)
        expected = total_s + SCENE_CLOSE_FADE_S
        drift = actual - expected
        if abs(drift) > _TOLERANCE_S:
            _logger.warning(
                "length_gate.scene_drift",
                scene_id=scene_id,
                expected=round(expected, 3),
                actual=round(actual, 3),
                drift=round(drift, 3),
            )
            raise TimingGateError(scene_id, expected=expected, actual=actual)
        _logger.info("length_gate.scene_passed", scene_id=scene_id, drift=round(drift, 3))
