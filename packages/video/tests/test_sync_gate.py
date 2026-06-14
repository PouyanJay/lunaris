"""Gate D tests (V3-T4): the sync gate checks that each spoken beat's frame at its audio midpoint
shows what the narration says, and fails CLEAN on a desync (no auto-repair — a re-plan is the V6
regenerate path, mirroring Gate C). Narrated-only: silent beats are never inspected.

Fakes stand in for vision and frame extraction; the gate's timeline math + fail-clean loop are real.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from lunaris_video.errors import SyncGateError
from lunaris_video.gates import SyncGate
from lunaris_video.schemas import SceneContracts, SyncVerdict, VoiceSpec
from lunaris_video.voice import StubSpeechSynthesizer

_VOICE = VoiceSpec(provider="elevenlabs", voice_id="v-test", model="eleven_multilingual_v2")
_DESYNC_REASON = "the frame lags the narration"


class _RecordingExtractor:
    """An ``ISyncFrameExtractor`` double: records the timestamps Gate D samples; returns bytes."""

    def __init__(self) -> None:
        self.timestamps: list[float] = []

    async def extract_at(self, mp4_path: Path, at_seconds: float) -> bytes:
        self.timestamps.append(at_seconds)
        return b"frame-bytes"


class _FakeSyncVision:
    """A vision double: every beat matches except the one at ``fail_at_ordinal`` (1-based, over the
    spoken beats in inspection order) — so a desync can be seeded in any scene, including a later
    one that only fires after the cross-scene cursor has accumulated."""

    def __init__(self, *, fail_at_ordinal: int | None = None) -> None:
        self._fail_at = fail_at_ordinal
        self.inspected: list[str] = []

    async def inspect(self, frame: bytes, *, narration: str, beat_id: str) -> SyncVerdict:
        self.inspected.append(beat_id)
        if len(self.inspected) == self._fail_at:
            return SyncVerdict(matches=False, reason=_DESYNC_REASON)
        return SyncVerdict(matches=True)


def _spoken_beat_ids(contract: SceneContracts) -> list[str]:
    return [beat.id for scene in contract.scenes for beat in scene.beats if beat.narration]


# Ordinal 2 desyncs in the first scene; ordinal 5 desyncs in the THIRD scene — the latter only fires
# after the gate has walked scenes 1+2, proving the cross-scene cursor accumulates on the fail path.
@pytest.mark.parametrize("fail_ordinal", [2, 5])
async def test_a_desynced_beat_is_caught(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path, fail_ordinal: int
) -> None:
    # Arrange — a real voiced manifest; one spoken beat's midpoint frame doesn't match its words.
    contract = make_lesson_contract()
    manifest = await StubSpeechSynthesizer().synthesize(contract, voice=_VOICE, audio_dir=tmp_path)
    vision = _FakeSyncVision(fail_at_ordinal=fail_ordinal)
    frames = _RecordingExtractor()

    # Act / Assert — the gate fails clean, naming the offending beat with the vision model's reason.
    with pytest.raises(SyncGateError) as excinfo:
        await SyncGate(vision=vision, frames=frames).check(
            tmp_path / "narrated.mp4", contract, manifest
        )
    assert excinfo.value.beat_id == _spoken_beat_ids(contract)[fail_ordinal - 1]
    assert excinfo.value.reason == _DESYNC_REASON
    # Fail-fast: the gate stopped at the first mismatch — no later beat was inspected or sampled.
    assert len(vision.inspected) == fail_ordinal
    assert len(frames.timestamps) == fail_ordinal


async def test_a_synced_video_passes_and_inspects_only_spoken_beats(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange — every beat's frame matches; the fixture has a silent b3 per scene.
    contract = make_lesson_contract()
    manifest = await StubSpeechSynthesizer().synthesize(contract, voice=_VOICE, audio_dir=tmp_path)
    vision = _FakeSyncVision()
    frames = _RecordingExtractor()

    # Act — no raise.
    await SyncGate(vision=vision, frames=frames).check(
        tmp_path / "narrated.mp4", contract, manifest
    )

    # Assert — only spoken beats were inspected, each sampled at its window midpoint on the GLOBAL
    # timeline. The expected midpoints are re-derived from the manifest the gate consumed (the same
    # algebra), then compared against frames.timestamps — a RECORDED output of the gate, not the
    # formula — so a cursor bug (e.g. advancing before taking the midpoint) would fail the match.
    spoken_ids: list[str] = []
    expected_midpoints: list[float] = []
    cursor = 0.0
    for scene in contract.scenes:
        timing_by_beat = {beat.id: beat for beat in manifest[scene.id].beats}
        for beat in scene.beats:
            window = timing_by_beat[beat.id].anim_s
            if timing_by_beat[beat.id].audio is not None and beat.narration.strip():
                spoken_ids.append(beat.id)
                expected_midpoints.append(round(cursor + window / 2, 4))
            cursor += window
    assert vision.inspected == spoken_ids
    assert [round(timestamp, 4) for timestamp in frames.timestamps] == expected_midpoints
