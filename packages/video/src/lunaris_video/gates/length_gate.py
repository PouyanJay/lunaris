from collections.abc import Awaitable, Callable
from pathlib import Path

import structlog

from lunaris_video.assembly import SCENE_CLOSE_FADE_S

_logger = structlog.get_logger(__name__)

# How far a scene's render may sit from its timeline before it counts as drift. The render duration
# is frame-quantized (~1/30s) and the beat windows are floats, so a few hundredths of a second of
# slack is pure quantization; a real over-budget beat or a missing closing fade is far larger
# (0.5s+ / 0.7s). This catches the latter without false-positiving on the former.
_TOLERANCE_S = 0.15

# The most a SHORT scene may be auto-padded (C3): up to this much missing tail is stretched to the
# audio window by freezing the last frame (a held closing frame), instead of shipping the gap as a
# desync. Beyond it, the render is structurally too short (a whole beat under-ran) — record the
# drift rather than papering over a real authoring problem with a long frozen frame.
_MAX_PAD_S = 2.0

# Injectable so the gate is testable with no real render: the composition root wires the sandboxed
# ffprobe; tests supply a stub. Private — callers inject the concrete probe, not this type.
_DurationProbe = Callable[[Path], Awaitable[float]]
# The pad seam (C3): freeze a short scene's last frame for the missing seconds, in place, returning
# whether it padded. Optional — a gate wired without one (e.g. a test) just records the drift.
_ScenePadder = Callable[[Path, float], Awaitable[bool]]


class LengthGate:
    """Gate 1 (deterministic, voiced-only): a scene's rendered video must be as long as its audio
    timeline — ``total_s`` (the sum of its beat windows) plus the ``SCENE_CLOSE_FADE_S`` closing
    fade — within a few frames.

    A mismatch means a beat's animations overran their window, or the closing fade is missing/extra,
    so the narration drifts against the visuals (and the error compounds across scenes). Unlike Gate
    D (the vision sync check), this is a single ``ffprobe`` with no model call, so it's a cheap
    deterministic measurement.

    C3: a scene that rendered slightly SHORT (within ``_MAX_PAD_S``) is AUTO-PADDED to its window —
    its last frame is held for the missing seconds — and re-measured, so a small short drift no
    longer ships as a desync. A long render (or a short one past the pad band, or a pad that failed)
    is recorded as before. ``evaluate`` returns the residual drift in seconds when it exceeds
    tolerance (else ``None``); the pipeline ships the video best-effort and records the drift in
    provenance — the voiceover is never dropped (every course carries narration).
    """

    def __init__(self, *, probe: _DurationProbe, pad: _ScenePadder | None = None) -> None:
        self._probe = probe
        self._pad = pad

    async def evaluate(self, scene_id: str, mp4_path: Path, total_s: float) -> float | None:
        expected = total_s + SCENE_CLOSE_FADE_S
        drift = round(await self._probe(mp4_path) - expected, 3)
        # C3 auto-pad: a scene short by a small, paddable amount is stretched to its audio window
        # (a held last frame) so the narration stays aligned, then re-measured. Only SHORT drift is
        # paddable — a long render cannot be trimmed without cutting the closing fade.
        if self._pad is not None and _TOLERANCE_S < -drift <= _MAX_PAD_S:
            drift = await self._pad_and_remeasure(scene_id, mp4_path, expected, missing=-drift)
        if abs(drift) > _TOLERANCE_S:
            _logger.warning(
                "length_gate.scene_drift",
                scene_id=scene_id,
                expected=round(expected, 3),
                drift=drift,
            )
            return drift
        _logger.info("length_gate.scene_passed", scene_id=scene_id, drift=drift)
        return None

    async def _pad_and_remeasure(
        self, scene_id: str, mp4_path: Path, expected: float, *, missing: float
    ) -> float:
        """Pad the short scene to ``expected`` and return the residual drift, or the unchanged drift
        if the pad did not fire (best-effort — a pad failure degrades, it never fails the job)."""
        assert self._pad is not None  # guarded by the caller
        if not await self._pad(mp4_path, missing):
            _logger.warning("length_gate.pad_failed", scene_id=scene_id)
            return round(-missing, 3)
        residual = round(await self._probe(mp4_path) - expected, 3)
        _logger.info(
            "length_gate.scene_padded",
            scene_id=scene_id,
            padded_by=round(missing, 3),
            drift=residual,
        )
        return residual
