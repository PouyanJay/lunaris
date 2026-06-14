"""Speech-synthesis tests (V3-T1).

The stub is the hermetic test double: it produces a MEASURED-shape ``TimingManifest`` — the same
shape the WPM estimate emits, but ``estimated=False`` with real clip paths and measured durations —
so a contract renders narrated or silent with no re-plan. The real ElevenLabs synthesizer is tested
through injected TTS + measurement seams (no network, no ffmpeg); its live path self-skips.
"""

import re
from collections.abc import Callable
from pathlib import Path

from lunaris_video.assembly import estimate_timing
from lunaris_video.schemas import SceneContracts, TimingManifest, VoiceSpec
from lunaris_video.skill import read_skill_asset
from lunaris_video.voice import ElevenLabsSpeechSynthesizer, StubSpeechSynthesizer
from lunaris_video.voice import elevenlabs_speech_synthesizer as es

_VOICE = VoiceSpec(provider="elevenlabs", voice_id="v-test", model="eleven_multilingual_v2")


async def test_stub_synthesizes_a_measured_manifest(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange
    contract = make_lesson_contract()

    # Act
    manifest = await StubSpeechSynthesizer().synthesize(contract, voice=_VOICE, audio_dir=tmp_path)

    # Assert — same scene/beat shape as the estimate, but measured: estimated False, clip on disk.
    assert isinstance(manifest, TimingManifest)
    assert set(manifest.scene_ids()) == {s.id for s in contract.scenes}
    for scene in contract.scenes:
        beats = manifest[scene.id].beats
        assert [b.id for b in beats] == [b.id for b in scene.beats]
        for beat, source in zip(beats, scene.beats, strict=True):
            assert beat.estimated is False
            if source.narration:
                assert beat.audio is not None
                assert (tmp_path / beat.audio).is_file()
                assert beat.audio_s > 0
            else:
                assert beat.audio_s == 0.0
                assert beat.audio is None


async def test_measured_durations_replace_the_estimate(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange — the audio-drives-video point: measured TTS durations REPLACE the WPM estimate, so a
    # spoken beat's window changes once voiced (same contract, a different audio-driven timeline).
    contract = make_lesson_contract()
    assert any(beat.narration for s in contract.scenes for beat in s.beats), (
        "fixture needs at least one spoken beat to compare measured vs estimated"
    )

    # Act
    estimated = estimate_timing(contract)
    measured = await StubSpeechSynthesizer().synthesize(contract, voice=_VOICE, audio_dir=tmp_path)

    # Assert — at least one spoken beat's measured length differs from its estimate.
    differs = any(
        measured[s.id].beats[i].audio_s != estimated[s.id].beats[i].audio_s
        for s in contract.scenes
        for i, beat in enumerate(s.beats)
        if beat.narration
    )
    assert differs, "measured timings must differ from the estimate (else audio isn't driving)"


async def test_real_synthesizer_speaks_each_beat_with_prosody_continuity(
    make_lesson_contract: Callable[..., SceneContracts], tmp_path: Path
) -> None:
    # Arrange — fake the TTS call and the duration measurement so the orchestration (per-beat loop,
    # neighbour text for continuity, silent-beat skip, clip-on-disk, manifest) is proven offline.
    spoken: list[tuple[str, str | None, str | None]] = []

    async def fake_tts(text: str, previous: str | None, following: str | None) -> bytes:
        spoken.append((text, previous, following))
        return b"fake-mp3-bytes"

    async def fake_measure(path: Path) -> float:
        return 2.0

    contract = make_lesson_contract()
    synth = ElevenLabsSpeechSynthesizer(api_key="sk_x", tts_client=fake_tts, measure=fake_measure)

    # Act
    manifest = await synth.synthesize(contract, voice=_VOICE, audio_dir=tmp_path)

    # Assert — one clip per spoken beat, the neighbour chain threaded for continuity (spanning scene
    # boundaries), measured manifest with silent beats left unspoken.
    texts = [b.narration for s in contract.scenes for b in s.beats if b.narration]
    assert len(spoken) == len(texts)
    assert spoken[0] == (texts[0], None, texts[1])
    # The interior beat carries BOTH neighbours — proves the chain, not just the boundaries.
    assert spoken[1] == (texts[1], texts[0], texts[2])
    assert spoken[-1] == (texts[-1], texts[-2], None)
    for scene in contract.scenes:
        for beat, source in zip(manifest[scene.id].beats, scene.beats, strict=True):
            assert beat.estimated is False
            if source.narration:
                assert beat.audio is not None and (tmp_path / beat.audio).is_file()
                assert beat.audio_s == 2.0
            else:
                assert beat.audio is None
                assert beat.audio_s == 0.0


def test_measured_path_constants_match_the_pinned_skill_script() -> None:
    # The skill's narration.py is the source of truth for the synthesize model; pin our pad/floor
    # to it so a future skill bump that changes them turns red instead of silently producing
    # measured timings that no longer line up beat-for-beat with the estimate they replace.
    narration = read_skill_asset("scripts/narration.py")

    pad = float(re.search(r'"--pad",\s*type=float,\s*default=(\d+(?:\.\d+)?)', narration).group(1))
    min_beat = float(re.search(r"MIN_BEAT_S\s*=\s*(\d+(?:\.\d+)?)", narration).group(1))

    assert pad == es._PAD_S
    assert min_beat == es._MIN_BEAT_S
